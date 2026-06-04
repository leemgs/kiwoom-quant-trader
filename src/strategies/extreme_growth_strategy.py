import gc
import numpy as np
import pandas as pd
import time
import logging
from .base_strategy import BaseStrategy
from core.leverage_manager import DynamicLeverageManager

class ExtremeGrowthStrategy(BaseStrategy):
    """
    지정된 자본금으로 지정된 기간 동안 목표 수익을 달성하기 위한 극단적 초단기/고위험 스캘핑 전략
    """
    def __init__(self, broker, universe, config, db=None):
        super().__init__(broker)
        self.universe = universe
        self.config = config.get('trading', {}).get('extreme_growth', {})
        self.take_profit = config.get('trading', {}).get('take_profit', 0.05)  # 익절: 5%
        self.db = db
        self.positions = {} # 현재 보유 포지션 관리

        initial_capital = config.get('trading', {}).get('investment_budget', 10000)
        self.initial_capital = initial_capital
        self.max_trading_limit = config.get('trading', {}).get('max_trading_limit', 100000)
        self.leverage_manager = DynamicLeverageManager(initial_capital=initial_capital)
        self._cash_balance_cache = {'value': None, 'time': 0}  # 예수금 캐시 (30초)

        self.holding_timeout = int(self.config.get('holding_timeout', 1800))  # 30분 기본값
        self.daily_open_prices = {}
        self.traded_today = set()
        self.current_date = time.strftime("%Y-%m-%d")

        # ─── 스마트 모멘텀 전략 파라미터 ──────────────────────────────────────
        # 진입 조건: 시가 대비 상승 임계값 (기본 1.5%) — 의미 있는 상승장에서만 진입
        self.breakout_threshold = float(self.config.get('breakout_threshold', 0.015))
        # 진입 조건: 연속 상승 틱 수 — N번 연속 가격이 올라야 매수 신호 확정
        self.momentum_ticks = int(self.config.get('momentum_ticks', 3))
        # 손절 조건: 고점 대비 하락 비율 (트레일링 스탑, 기본 1.5%)
        self.trailing_stop_pct = float(self.config.get('trailing_stop', 0.015))

        # 종목별 최근 가격 이력 (deque, 모멘텀 계산용)
        from collections import deque as _deque
        self._deque = _deque
        self.price_history = {}   # code -> deque[float]
        # 종목별 포지션 보유 이후 최고가 (트레일링 스탑 기준가)
        self.trailing_high = {}   # code -> float
        
    def get_real_cash_balance(self):
        """실제 계좌 예수금(현금) 조회 (30초 캐시 적용, 오류 시 기존 캐시 재사용 혹은 초기자본 반환)"""
        now = time.time()
        if self._cash_balance_cache['value'] is not None and now - self._cash_balance_cache['time'] < 30:
            return self._cash_balance_cache['value']
        try:
            # fetch_balance()는 output2에 계좌 종합 정보(예수금 포함)를 담아 반환
            res = self.broker.api.fetch_balance()
            if isinstance(res, dict) and res.get('rt_cd') == '0':
                output2 = res.get('output2', [])
                if output2 and len(output2) > 0:
                    cash = int(output2[0].get('dnca_tot_amt', 0))  # 예수금 총액
                    total_assets = int(output2[0].get('tot_evlu_amt', cash))
                    if cash > 0:
                        self._cash_balance_cache = {'value': cash, 'time': now}
                        logging.info(f"💳 [예수금 조회] 실제 계좌 예수금: {cash:,}원")
                        self.save_balance_to_file(cash, total_assets)
                        return cash
            
            # API 응답 오류 또는 빈 응답인 경우 경고 출력 후 캐시값 재사용 시도
            msg = res.get('msg1', '데이터가 비어 있습니다') if isinstance(res, dict) else '응답 오류'
            # 실패하더라도 다음 종목 루프에서 연쇄 호출되는 것을 방지하기 위해 캐시 시간만 갱신
            self._cash_balance_cache['time'] = now
            if self._cash_balance_cache['value'] is not None:
                logging.warning(f"⚠️ 계좌 예수금 조회 실패 ({msg}). 기존 캐시값({self._cash_balance_cache['value']:,}원)을 유지합니다.")
                return self._cash_balance_cache['value']
        except Exception as e:
            # 실패하더라도 다음 종목 루프에서 연쇄 호출되는 것을 방지하기 위해 캐시 시간만 갱신
            self._cash_balance_cache['time'] = now
            if self._cash_balance_cache['value'] is not None:
                logging.warning(f"⚠️ 계좌 예수금 조회 에러: {e}. 기존 캐시값({self._cash_balance_cache['value']:,}원)을 유지합니다.")
                return self._cash_balance_cache['value']
            logging.warning(f"⚠️ 계좌 예수금 조회 실패: {e}. 초기자본({self.initial_capital:,}원)으로 대체합니다.")
        
        # 폴백: initial_capital 사용
        return self.initial_capital

    def save_balance_to_file(self, cash, total_assets):
        """계좌 잔고 및 총자산 정보를 로컬 파일 캐시(data/balance_cache.json)에 저장 (대시보드와 공유)"""
        try:
            import json
            import os
            os.makedirs("data", exist_ok=True)
            data = {
                "cash": cash,
                "total_assets": total_assets,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            with open("data/balance_cache.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.warning(f"⚠️ balance_cache.json 저장 실패: {e}")

    # ─── 스마트 모멘텀 진입 신호 ──────────────────────────────────────────────
    def _update_and_check_momentum(self, code: str, current_price: float) -> bool:
        """종목 가격 이력을 업데이트하고 N틱 연속 상승 모멘텀이 확인되면 True 반환.

        Args:
            code: 종목코드
            current_price: 현재가
        Returns:
            True  — momentum_ticks 번 연속으로 가격이 올라 매수 신호 확정
            False — 아직 데이터 부족 또는 상승 추세 미확인
        """
        if code not in self.price_history:
            self.price_history[code] = self._deque(maxlen=self.momentum_ticks + 1)
        self.price_history[code].append(current_price)

        history = self.price_history[code]
        if len(history) < self.momentum_ticks:
            return False  # 아직 충분한 이력 없음

        # 마지막 momentum_ticks 개의 가격이 모두 직전보다 높아야 상승 추세
        prices = list(history)[-self.momentum_ticks:]
        for i in range(1, len(prices)):
            if prices[i] <= prices[i - 1]:
                return False
        return True

    def sync_positions_with_account(self):
        """실제 증권 계좌의 잔고(보유 종목)와 메모리 포지션(self.positions) 동기화 (고스트 포지션 방지)"""
        try:
            res = self.broker.api.fetch_balance()
            if isinstance(res, dict) and res.get('rt_cd') == '0':
                output1 = res.get('output1', [])
                actual_holdings = {}
                for item in output1:
                    code = item.get('pdno')  # 종목코드
                    qty = int(item.get('hldg_qty', 0))
                    buy_price = int(float(item.get('pchs_avg_pric', 0)))
                    if code and qty > 0:
                        actual_holdings[code] = {
                            'qty': qty,
                            'buy_price': buy_price,
                            'buy_time': time.time()  # 실제 매수 시점은 알 수 없으므로 현재 시간으로 설정
                        }
                
                # 대시보드 및 봇 내부 캐시 동기화를 위해 예수금 정보도 함께 저장
                output2 = res.get('output2', [])
                if output2 and len(output2) > 0:
                    cash = int(output2[0].get('dnca_tot_amt', 0))
                    total_assets = int(output2[0].get('tot_evlu_amt', cash))
                    if cash > 0:
                        self._cash_balance_cache = {'value': cash, 'time': time.time()}
                        self.save_balance_to_file(cash, total_assets)

                # 메모리의 포지션을 실제 계좌 잔고와 비교하여 동기화
                # 1. 실제 계좌에는 없는데 메모리에 있는 종목 (고스트 포지션) 제거
                for code in list(self.positions.keys()):
                    if code not in actual_holdings:
                        logging.warning(f"⚠️ [잔고 동기화] 실제 계좌에 없는 고스트 포지션 제거: {code}")
                        del self.positions[code]
                
                # 2. 실제 계좌에 있는 종목을 메모리에 등록/업데이트
                for code, holding in actual_holdings.items():
                    if code not in self.positions:
                        logging.info(f"📥 [잔고 동기화] 실제 보유 종목 포지션 등록: {code} ({holding['qty']}주, 평단가: {holding['buy_price']}원)")
                        self.positions[code] = holding
                    else:
                        # 수량이나 평단가가 다를 경우 업데이트
                        if self.positions[code]['qty'] != holding['qty'] or abs(self.positions[code]['buy_price'] - holding['buy_price']) > 5:
                            logging.info(f"🔄 [잔고 동기화] 포지션 정보 업데이트: {code} ({self.positions[code]['qty']}주 -> {holding['qty']}주, {self.positions[code]['buy_price']}원 -> {holding['buy_price']}원)")
                            self.positions[code]['qty'] = holding['qty']
                            self.positions[code]['buy_price'] = holding['buy_price']
                
                logging.info(f"✅ [잔고 동기화] 계좌 실잔고 동기화 완료 (현재 보유: {len(self.positions)}종목)")
        except Exception as e:
            logging.error(f"❌ [잔고 동기화] 계좌 잔고 동기화 중 오류 발생: {e}")

    def check_signal(self, code, df):
        """BaseStrategy의 추상 메서드 구현. 해당 전략은 run()에서 자체 로직을 사용하므로 여기서는 사용하지 않음."""
        return False
        
    def smart_order_routing(self, code, target_qty, order_type="BUY", current_price=0, orderbook=None):
        """시장가(Taker) 대신 최적의 호가에 지정가(Maker)로 깔아 수수료 및 슬리피지 방어"""
        # [강건성 개선] 초단기 스캘핑 전략에서는 체결 신속성과 고스트 포지션 방지를 위해 항상 시장가 주문("01" / "02")을 전송합니다.
        # 지정가 주문은 미체결 상태에서 로컬 포지션만 먼저 등록되는 결함을 유발하므로 사용하지 않습니다.
        broker_order_type = "01" if order_type == "BUY" else "02"
        return self.broker.send_order(code, target_qty, order_type=broker_order_type, price=0)

    def scan_event_driven_news(self, current_news_feed):
        """DART 공시 및 뉴스 속보를 스크래핑하여 즉각 반응 (임상성공, 무상증자 등)"""
        if not hasattr(self, 'seen_news'):
            self.seen_news = set()
            
        keywords = ["무상증자", "임상 성공", "경영권 분쟁", "공급계약", "상한가"]
        for news in current_news_feed:
            if any(keyword in news['title'] for keyword in keywords):
                news_id = f"{news['code']}_{news['title']}"
                if news_id not in self.seen_news:
                    logging.info(f"🔥 [초강력 재료 포착] {news['code']} - {news['title']} (0.1초 내 진입 시도)")
                    self.seen_news.add(news_id)
                    return news['code']
        return None

    def analyze_micro_scalping_orderbook(self, code, orderbook_data):
        """호가창의 매도벽이 순식간에 허물어지는 스푸핑/체결강도 폭발 시점 감지"""
        if orderbook_data['trade_intensity'] > 200.0 and orderbook_data['ask_remains'] > orderbook_data['bid_remains'] * 3:
            return True
        return False

    def decide_limit_up_overnight(self, code, current_price, limit_up_price, orderbook_data):
        """상한가(+29.5% 이상)에 진입하고 상한가 매수잔량이 견고한 경우 오버나잇 (당일 매도 예외)"""
        if not self.config.get('limit_up_overnight', False):
            return False
            
        is_near_limit_up = current_price >= limit_up_price * 0.995
        is_strong_bid_wall = orderbook_data['limit_bid_remains'] > orderbook_data['total_volume'] * 0.1
        
        if is_near_limit_up and is_strong_bid_wall:
            logging.info(f"🔒 [점상 오버나잇 모드] {code} 상한가 굳히기 포착. 당일 매도를 취소하고 명일 시초가까지 홀딩합니다.")
            return True
        return False

    def monitor_position(self, code):
        """보유 포지션 실시간 익절/트레일링스탑 감시 (실시간 현재가 조회)

        [트레일링 스탑 전략]
        - 고점 갱신 시 trailing_high[code]를 끌어올림
        - 현재가가 고점 대비 trailing_stop_pct 이상 하락하면 청산
          → 수익이 쌓일수록 손절선이 올라가 수익을 보호
        - 익절(take_profit_price)에 도달하면 전량 즉시 익절
        """
        if code not in self.positions:
            return

        pos = self.positions[code]
        buy_price = pos['buy_price']
        qty = pos['qty']

        # 실시간 현재가 조회 (오류 시 이전 상태 보존 및 다음 기회로 미룸)
        try:
            current_price = self.broker.get_price(code)
            if current_price <= 0:
                raise ValueError("현재가가 0원 이하입니다.")
            current_price = int(current_price)
        except Exception as e:
            logging.warning(f"⚠️ [{code}] 포지션 실시간 가격 조회 실패: {e}")
            return

        profit = (current_price - buy_price) * qty

        # ── 1. 익절 조건: 목표가 도달 시 즉시 청산 ──────────────────────────
        take_profit_price = int(buy_price * (1 + self.take_profit))
        if current_price >= take_profit_price:
            self.sell_position(code, current_price, profit, reason=f"익절 +{self.take_profit*100:.1f}% 달성")
            return

        # ── 2. 트레일링 스탑: 고점 추적 후 되돌림 시 청산 ──────────────────
        # 진입 이후 최고가를 갱신하며 스탑 기준가를 자동으로 끌어올림
        if code not in self.trailing_high:
            self.trailing_high[code] = buy_price
        if current_price > self.trailing_high[code]:
            self.trailing_high[code] = current_price
            logging.info(f"📈 [{code}] 고점 갱신: {current_price:,}원 "
                         f"(스탑 기준가 → {int(current_price * (1 - self.trailing_stop_pct)):,}원)")

        trailing_stop_price = int(self.trailing_high[code] * (1 - self.trailing_stop_pct))
        if current_price <= trailing_stop_price:
            peak_gain_pct = (self.trailing_high[code] - buy_price) / buy_price * 100
            self.sell_position(
                code, current_price, profit,
                reason=f"트레일링 스탑 (고점 {self.trailing_high[code]:,}원에서 {self.trailing_stop_pct*100:.1f}% 하락, 최고 상승률 {peak_gain_pct:+.2f}%)"
            )
            return

        # ── 3. 시간 초과 청산 ────────────────────────────────────────────────
        if time.time() - pos['buy_time'] > self.holding_timeout:
            self.sell_position(code, current_price, profit,
                               reason=f"시간 경과 청산 ({self.holding_timeout}초)")

    def sell_position(self, code, current_price=50000, profit=0, reason=""):
        if code not in self.positions:
            return
            
        pos = self.positions[code]
        qty = pos['qty']
        
        logging.info(f"⚖️ [포지션 청산] {code} 매도 진행 ({reason}): 매도가 {current_price}원, 손익 {profit:+,}원")
        # 실제 매도 주문 전송
        res = self.broker.send_sell_order(code, qty, current_price, order_type="01")
        
        # API 응답 확인: 실전/모의 API 응답 코드(rt_cd)가 '0'일 때만 DB 기록 및 포지션 제거
        if isinstance(res, dict) and res.get('rt_cd') == '0':
            # DB에 매도 기록
            if self.db:
                self.db.log_trade(code, "SELL", qty, current_price, profit=profit)
                
            # 레버리지 매니저 피드백 반영
            profit_pct = profit / (pos['buy_price'] * qty)
            self.leverage_manager.update_trade_result(is_win=(profit > 0), profit_pct=profit_pct)
            
            # 예수금 캐시 즉각 무효화 및 당일 매매 종목 추가
            self._cash_balance_cache = {'value': None, 'time': 0}
            self.traded_today.add(code)

            # 트레일링 스탑 / 가격 이력 상태 정리
            self.trailing_high.pop(code, None)
            self.price_history.pop(code, None)

            # 포지션 삭제
            del self.positions[code]
            logging.info(f"✅ [{code}] 매도 청산 완료, 당일 재진입 제한(Traded Today) 및 DB 기록 성공!")
        else:
            msg = res.get('msg1', '알 수 없는 오류') if isinstance(res, dict) else '응답 없음'
            logging.error(f"❌ [{code}] 매도 청산 주문 실패 (API 오류): {msg}")
            
            # 계좌 잔고 불일치 등의 이유로 청산이 계속 실패하는 고스트 포지션은 목록에서 제거
            if isinstance(res, dict) and ('잔고' in msg or '수량' in msg or 'KIOK' in res.get('msg_cd', '')):
                logging.warning(f"⚠️ [{code}] 계좌 잔고 불일치 감지. 고스트 포지션을 강제로 목록에서 제거합니다.")
                del self.positions[code]

    def load_open_positions_from_db(self):
        """DB의 거래 이력을 바탕으로 미청산된 포지션을 로드하여 실시간 익절/손절 감시 대상에 등록"""
        if not self.db:
            return
            
        try:
            df = self.db.get_all_trades(limit=2000)  # 전체 로드 대신 최근 2000건만
            if df.empty:
                return

            holdings = {}
            df_sorted = df.copy()
            df_sorted['timestamp'] = pd.to_datetime(df_sorted['timestamp'])
            df_sorted = df_sorted.sort_values('timestamp')
            del df  # 원본 즉시 해제

            for _, row in df_sorted.iterrows():
                code = row['code']
                trade_type = row['type']
                qty = int(row['qty'])
                price = float(row['price'])
                timestamp_val = row['timestamp'].timestamp()

                if code not in holdings:
                    holdings[code] = {'qty': 0, 'total_cost': 0.0, 'buy_time': timestamp_val}

                if trade_type == 'BUY':
                    holdings[code]['qty'] += qty
                    holdings[code]['total_cost'] += qty * price
                    holdings[code]['buy_time'] = timestamp_val
                elif trade_type == 'SELL':
                    if holdings[code]['qty'] > 0:
                        avg_price = holdings[code]['total_cost'] / holdings[code]['qty']
                        holdings[code]['qty'] = max(0, holdings[code]['qty'] - qty)
                        holdings[code]['total_cost'] = holdings[code]['qty'] * avg_price

            del df_sorted  # 정렬 DataFrame 해제

            for code, h in holdings.items():
                if h['qty'] > 0:
                    buy_price = int(h['total_cost'] / h['qty'])
                    self.positions[code] = {
                        'qty': h['qty'],
                        'buy_price': buy_price,
                        'buy_time': h['buy_time']
                    }
                    logging.info(f"📥 [포지션 복구] DB에서 미청산 포지션 복구 완료: {code} (수량: {h['qty']}주, 평단가: {buy_price}원)")
            gc.collect()
        except Exception as e:
            logging.error(f"Error loading open positions from DB: {e}")

    def run(self):
        logging.info("🚀 [Extreme Growth 1,000% 목표 모드] 엔진 가동. 미수 풀레버리지/스캘핑 시스템 시작.")
        # 1. DB로부터 미청산 포지션 동기화 및 복구
        self.load_open_positions_from_db()
        # 2. 실제 증권 계좌 잔고와 비교하여 동기화 (고스트 포지션 제거 및 누락 포지션 추가)
        self.sync_positions_with_account()
        self._last_sync_time = time.time()
        
        while True:
            # 0. 날짜가 변경되었을 때 일일 데이터 초기화 (다중 영업일 지원)
            today_str = time.strftime("%Y-%m-%d")
            if today_str != self.current_date:
                logging.info(f"📅 [날짜 변경] {self.current_date} -> {today_str}. 일일 상태값(시가, 당일 매매 이력)을 초기화합니다.")
                self.current_date = today_str
                self.daily_open_prices = {}
                self.traded_today = set()

            # 5분마다 실제 증권 계좌 잔고와 메모리 포지션 재동기화 (레이스 컨디션 및 체결 누락 보정)
            if time.time() - self._last_sync_time > 300:
                self.sync_positions_with_account()
                self._last_sync_time = time.time()

            current_time = time.strftime("%H:%M:%S")
            is_after_market_close = current_time >= "15:15:00"
            
            # 1. 15:15 미수 동결 방지 강제 청산 체크
            if self.leverage_manager.enforce_margin_liquidation(current_time):
                if not getattr(self, 'liquidation_triggered', False):
                    logging.warning("⚠️ [리스크 관리] 장 마감 임박. 미체결 주문 취소 및 전 종목 강제 청산 (시장가 주문으로 변경 적용)")
                    self.liquidation_triggered = True
                    # 미체결 주문 취소 시도
                    try:
                        if hasattr(self.broker, 'cancel_all_orders'):
                            self.broker.cancel_all_orders()
                    except Exception as e:
                        logging.error(f"미체결 주문 취소 실패: {e}")
                    
                    # 보유한 모든 포지션 강제 청산 (시장가)
                    for code in list(self.positions.keys()):
                        try:
                            # 시장가 매도를 위한 현재가 로드
                            current_price = self.broker.get_price(code) if hasattr(self.broker, 'get_price') else 50000
                            pos = self.positions[code]
                            profit = (current_price - pos['buy_price']) * pos['qty']
                            self.sell_position(code, current_price=current_price, profit=profit, reason="장 마감 강제 청산")
                        except Exception as e:
                            logging.error(f"{code} 장 마감 강제 청산 실패: {e}")
                pass
            else:
                self.liquidation_triggered = False

            # 보유 포지션 실시간 익절/손절 감시
            for code in list(self.positions.keys()):
                self.monitor_position(code)

            for code in self.universe:
                # 이미 보유한 종목은 스킵
                if code in self.positions:
                    continue
                
                # 당일 한번 거래 완료한 종목은 과도한 수수료 차감을 막기 위해 스킵 (1일 1회 매매 제한)
                if code in self.traded_today:
                    continue
                    
                # 15:15 이후에는 신규 매수 금지
                if is_after_market_close:
                    continue
                    
                # API를 통해 실시간 현재가 수신 (10초 캐시 적용)
                try:
                    if not hasattr(self, 'price_cache'):
                        self.price_cache = {}
                    
                    if code not in self.price_cache or time.time() - self.price_cache[code]['time'] > 10:
                        real_prpr = self.broker.get_price(code)
                        if real_prpr and real_prpr > 0:
                            self.price_cache[code] = {
                                'price': int(real_prpr),
                                'time': time.time()
                            }
                        else:
                            logging.warning(f"⚠️ [{code}] KIS API 현재가 조회 실패 (0원 반환). 해당 종목 매매를 건너뜁니다.")
                            continue
                    current_price = self.price_cache[code]['price']
                except Exception as e:
                    logging.warning(f"⚠️ [{code}] KIS API 현재가 조회 에러: {e}. 해당 종목 매매를 건너뜁니다.")
                    continue
                
                # 실제 계좌 예수금 기반으로 1주도 살 수 없으면 스킵
                real_cash = self.get_real_cash_balance()
                if current_price > real_cash:
                    logging.warning(f"⚠️ [{code}] 현재가({current_price:,}원)가 실제 예수금({real_cash:,}원)보다 높아 매수 불가. (종목 제외됨)")
                    continue
                    
                limit_up_price = int(current_price * 1.3)

                # ── 당일 시가(Daily Open) 기준 설정 ──────────────────────────
                # 장 초반(09:00-09:05 KST)에 처음 관측한 가격을 시가로 확정.
                # 장 이후 봇이 시작된 경우: 처음 관측 가격 그대로 사용하되 로그 명시.
                if code not in self.daily_open_prices:
                    self.daily_open_prices[code] = current_price
                    logging.info(f"📋 [{code}] 당일 시가(기준가) 설정: {current_price:,}원")

                open_price = self.daily_open_prices[code]
                price_change_from_open = (current_price - open_price) / open_price if open_price > 0 else 0

                # ── [스마트 진입 신호] 2중 필터 ────────────────────────────────
                # 조건 A: 시가 대비 breakout_threshold(기본 1.5%) 이상 상승
                is_above_threshold = price_change_from_open >= self.breakout_threshold

                # 조건 B: 최근 momentum_ticks(기본 3번) 연속으로 가격이 상승 중
                #   - 가격 이력을 누적하며 상승 추세가 확인된 경우에만 매수 허용
                #   - 단발성 급등(스푸핑 등) 후 즉시 하락하는 종목 필터링
                is_rising_trend = self._update_and_check_momentum(code, current_price)

                # 두 조건을 모두 충족해야 매수 신호 확정
                is_breakout = is_above_threshold and is_rising_trend

                if is_breakout:
                    logging.info(
                        f"🚀 [{code}] 스마트 진입 신호 확정! "
                        f"시가 대비 +{price_change_from_open*100:.2f}% (임계값 {self.breakout_threshold*100:.1f}%), "
                        f"{self.momentum_ticks}틱 연속 상승 확인"
                    )

                # 뉴스는 실제 DART API 미연동 상태이므로 비활성화
                news_target = None

                # 2. 돌파 신호 확인 (뉴스 또는 스마트 모멘텀 돌파)
                if news_target == code or is_breakout:
                    # 실제 계좌 예수금 및 총 자산 산출
                    real_cash = self.get_real_cash_balance()
                    
                    # DB 기반으로 열린 포지션들의 매수 원금을 계산
                    open_positions_cost = self.db.get_open_positions_cost() if self.db else sum(
                        pos['qty'] * pos['buy_price'] for pos in self.positions.values()
                    )
                    
                    total_assets = real_cash + open_positions_cost
                    
                    # 최대 허용 한도에서 이미 투자된 금액을 뺀 가용 한도
                    limit_based_available = max(0.0, self.max_trading_limit - open_positions_cost) if self.max_trading_limit else real_cash
                    
                    # 실제 가용 원금은 실제 예수금과 한도 중 작은 값
                    available_capital = min(real_cash, limit_based_available)

                    # 켈리 공식 및 미수 레버리지 자금 할당 (총 자산을 기준으로 베팅 비율 산출)
                    budget = self.leverage_manager.get_optimal_budget(
                        current_account_balance=total_assets, 
                        use_margin=self.config.get('use_margin_leverage', True)
                    )
                    
                    # 실제 가용 원금(레버리지 고려)을 초과할 수 없도록 한도 적용
                    max_allowed_budget = available_capital
                    if self.config.get('use_margin_leverage', True) and self.leverage_manager.calculate_kelly_fraction() > 0.3:
                        max_allowed_budget = available_capital * self.leverage_manager.max_margin_rate
                        
                    budget = min(budget, max_allowed_budget)
                    
                    # 목표 수량 계산
                    target_qty = int(budget / current_price)
                    
                    # [결함 해결] 가용 예수금(현금)을 초과할 수 없도록 엄격한 자금 상한(Cap) 설정
                    if target_qty * current_price > real_cash:
                        target_qty = int(real_cash / current_price)
                    
                    if target_qty > 0:
                        expected_required_capital = target_qty * current_price
                        logging.info(f"💰 [자금관리] 켈리 베팅 기반 진입 시도: 목표 예산 {budget:,.0f}원 (주문: {target_qty}주, 예상 필요 자금: {expected_required_capital:,.0f}원, 가용 예수금: {real_cash:,.0f}원)")
                        
                        # 스마트 주문 라우팅
                        res = self.smart_order_routing(code, target_qty, "BUY", current_price, orderbook=None)
                        
                        # API 응답 확인: 실전/모의 API 응답 코드(rt_cd)가 '0'일 때만 포지션 등록 및 DB 기록
                        if isinstance(res, dict) and res.get('rt_cd') == '0':
                            # 포지션 등록 및 DB 기록
                            self.positions[code] = {
                                'qty': target_qty,
                                'buy_price': current_price,
                                'buy_time': time.time()
                            }
                            if self.db:
                                self.db.log_trade(code, "BUY", target_qty, current_price, profit=0)
                                
                            # [결함 해결] 예수금 변경으로 인한 캐시 강제 무효화
                            self._cash_balance_cache = {'value': None, 'time': 0}
                            
                            logging.info(f"✅ [{code}] 매수 주문 접수 및 포지션 등록 성공! (수량: {target_qty}주, 진입가: {current_price:,}원)")
                        else:
                            msg = res.get('msg1', '알 수 없는 오류') if isinstance(res, dict) else '응답 없음'
                            logging.error(f"❌ [{code}] 매수 주문 실패 (API 오류): {msg}")
                    else:
                        # 예산 부족 로그 (최초 1회만 출력되도록 처리)
                        if not hasattr(self, 'insufficient_budget_logged'):
                            self.insufficient_budget_logged = set()
                        if code not in self.insufficient_budget_logged:
                            expected_required_capital = current_price # 최소 1주 매수에 필요한 예상 자금
                            if open_positions_cost > 0 and available_capital < current_price:
                                logging.info(f"⏸️ [자금관리] {code} 주문 대기: 현재 보유 종목으로 인해 가용 예산이 부족합니다 (현재가: {current_price}원, 가용 예산: {budget:,.0f}원).")
                            else:
                                logging.warning(f"⚠️ [자금관리] 예산 부족으로 {code} 주문 불가 (현재가: {current_price}원, 가용 예산: {budget:,.0f}원, 예상 필요 자금: {expected_required_capital:,.0f}원). '.env' 파일의 INVESTMENT_BUDGET을 늘려주세요.")
                            self.insufficient_budget_logged.add(code)

                # (루프 간 지연 방지용)
                time.sleep(0.1)

            # 유니버스 전체 순회 후 서버 부하 방지 및 가비지 컬렉션
            gc.collect()
            time.sleep(2.0)
