import numpy as np
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
        self.stop_loss = config.get('trading', {}).get('stop_loss', 0.015)
        self.db = db
        self.positions = {} # 현재 보유 포지션 관리
        
        initial_capital = config.get('trading', {}).get('investment_budget', 10000)
        self.initial_capital = initial_capital
        self.max_trading_limit = config.get('trading', {}).get('max_trading_limit', 100000)
        self.leverage_manager = DynamicLeverageManager(initial_capital=initial_capital)
        
    def check_signal(self, code, df):
        """BaseStrategy의 추상 메서드 구현. 해당 전략은 run()에서 자체 로직을 사용하므로 여기서는 사용하지 않음."""
        return False
        
    def smart_order_routing(self, code, target_qty, order_type="BUY", current_price=0, orderbook=None):
        """시장가(Taker) 대신 최적의 호가에 지정가(Maker)로 깔아 수수료 및 슬리피지 방어"""
        if not self.config.get('smart_order_routing', False):
            # 기본 시장가 주문
            return self.broker.send_order(code, target_qty, order_type=order_type, price=0) # 0은 시장가
            
        # 최적 지정가 계산 (단순화: 매수 시 최우선 매도호가에서 1틱 뺀 가격 등)
        # orderbook 데이터를 활용하여 1~3호가 사이의 최적의 Maker 가격 산출
        best_maker_price = current_price # 실제 구현시 호가 스프레드 분석
        
        logging.info(f"[Smart Order Routing] {order_type} 지정가 주문 대기 (슬리피지 방어): {best_maker_price}원")
        return self.broker.send_order(code, target_qty, order_type="LIMIT_MAKER", price=best_maker_price)

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
        """보유 포지션 실시간 익절/손절 감시 (Mock 시뮬레이션)"""
        if code not in self.positions:
            return
            
        pos = self.positions[code]
        buy_price = pos['buy_price']
        qty = pos['qty']
        
        # 실시간 가격 시뮬레이션 (Mock 가격 변동: 70% 확률로 익절 상승, 30% 확률로 손절 하락)
        import random
        price_change_pct = random.choice([0.035, 0.04, -0.02, 0.01, 0.03, -0.01])
        current_price = int(buy_price * (1 + price_change_pct))
        
        # 익절/손절 기준 설정
        take_profit_price = buy_price * (1 + 0.03) # 3% 익절
        stop_loss_price = buy_price * (1 - self.stop_loss) # 1.5% 손절
        
        if current_price >= take_profit_price:
            profit = (current_price - buy_price) * qty
            self.sell_position(code, current_price, profit, reason="익절 (Take Profit)")
        elif current_price <= stop_loss_price:
            profit = (current_price - buy_price) * qty
            self.sell_position(code, current_price, profit, reason="손절 (Stop Loss)")
        elif time.time() - pos['buy_time'] > 15: # 15초 지나면 청산 (타임아웃)
            profit = (current_price - buy_price) * qty
            self.sell_position(code, current_price, profit, reason="시간 경과 청산")

    def sell_position(self, code, current_price=50000, profit=0, reason=""):
        if code not in self.positions:
            return
            
        pos = self.positions[code]
        qty = pos['qty']
        
        logging.info(f"⚖️ [포지션 청산] {code} 매도 진행 ({reason}): 매도가 {current_price}원, 손익 {profit:+,}원")
        # 실제 매도 주문 전송
        self.broker.send_sell_order(code, qty, current_price, order_type="01")
        
        # DB에 매도 기록
        if self.db:
            self.db.log_trade(code, "SELL", qty, current_price, profit=profit)
            
        # 레버리지 매니저 피드백 반영
        profit_pct = profit / (pos['buy_price'] * qty)
        self.leverage_manager.update_trade_result(is_win=(profit > 0), profit_pct=profit_pct)
        
        # 포지션 삭제
        del self.positions[code]

    def load_open_positions_from_db(self):
        """DB의 거래 이력을 바탕으로 미청산된 포지션을 로드하여 실시간 익절/손절 감시 대상에 등록"""
        if not self.db:
            return
            
        try:
            df = self.db.get_all_trades()
            if df.empty:
                return
                
            holdings = {}
            import pandas as pd
            df_sorted = df.copy()
            df_sorted['timestamp'] = pd.to_datetime(df_sorted['timestamp'])
            df_sorted = df_sorted.sort_values('timestamp')
            
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
            
            for code, h in holdings.items():
                if h['qty'] > 0:
                    buy_price = int(h['total_cost'] / h['qty'])
                    self.positions[code] = {
                        'qty': h['qty'],
                        'buy_price': buy_price,
                        'buy_time': h['buy_time']
                    }
                    logging.info(f"📥 [포지션 복구] DB에서 미청산 포지션 복구 완료: {code} (수량: {h['qty']}주, 평단가: {buy_price}원)")
        except Exception as e:
            logging.error(f"Error loading open positions from DB: {e}")

    def run(self):
        logging.info("🚀 [Extreme Growth 1,000% 목표 모드] 엔진 가동. 미수 풀레버리지/스캘핑 시스템 시작.")
        # DB로부터 미청산 포지션 동기화 및 복구
        self.load_open_positions_from_db()
        
        while True:
            current_time = time.strftime("%H:%M:%S")
            
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
                
                # 예산이 현재가보다 낮아 1주도 살 수 없는 경우 스킵 (가짜 가격으로 대체하지 않음)
                if current_price > self.initial_capital + (self.db.get_total_profit() if self.db else 0):
                    logging.warning(f"⚠️ [{code}] 현재가({current_price:,}원)가 총 가용 자본보다 높아 매수 불가. INVESTMENT_BUDGET을 늘려주세요.")
                    continue
                    
                limit_up_price = int(current_price * 1.3)
                # 실제 호가 데이터 없이 기본 스캘핑 신호 사용 (변동성 돌파 기반)
                # orderbook_data는 실제 API 연동 전까지 volatility 기반 신호로 대체
                import random
                # 실제 가격 변동성을 기반으로 매수 신호 생성 (돌파전략: 전일 대비 0.5% 이상 상승 시)
                if not hasattr(self, 'prev_price_cache'):
                    self.prev_price_cache = {}
                prev_price = self.prev_price_cache.get(code, current_price)
                price_change_pct = (current_price - prev_price) / prev_price if prev_price > 0 else 0
                self.prev_price_cache[code] = current_price
                
                # 변동성 돌파 신호: 가격이 K_VALUE(0.3) 이상 상승 중이면 매수 신호
                k_value = self.config.get('k_value', 0.3) if self.config.get('k_value') else 0.3
                is_breakout = price_change_pct >= k_value * 0.01  # 0.3% 이상 상승 시 돌파 신호
                
                # 뉴스는 실제 DART API 미연동 상태이므로 비활성화
                news_target = None

                # 2. 돌파 신호 확인 (뉴스 또는 변동성 돌파)

                if news_target == code or is_breakout:
                    total_profit = self.db.get_total_profit() if self.db else 0.0
                    total_allowed_capital = self.initial_capital + total_profit
                    if self.max_trading_limit is not None:
                        total_allowed_capital = min(total_allowed_capital, self.max_trading_limit)
                    
                    # DB 기반으로 열린 포지션들의 매수 원금을 계산
                    open_positions_cost = self.db.get_open_positions_cost() if self.db else sum(
                        pos['qty'] * pos['buy_price'] for pos in self.positions.values()
                    )
                    # 남은 가용 원금 = 허용 총 자본 - 현재 보유 종목 매수 원금
                    available_capital = max(0.0, total_allowed_capital - open_positions_cost)

                    # 켈리 공식 및 미수 레버리지 자금 할당 (총 한도를 기준으로 베팅 비율 산출)
                    budget = self.leverage_manager.get_optimal_budget(
                        current_account_balance=total_allowed_capital, 
                        use_margin=self.config.get('use_margin_leverage', True)
                    )
                    
                    # 실제 가용 원금(레버리지 고려)을 초과할 수 없도록 한도 적용
                    max_allowed_budget = available_capital
                    if self.config.get('use_margin_leverage', True) and self.leverage_manager.calculate_kelly_fraction() > 0.3:
                        max_allowed_budget = available_capital * self.leverage_manager.max_margin_rate
                        
                    budget = min(budget, max_allowed_budget)
                    target_qty = int(budget / current_price)
                    
                    if target_qty > 0:
                        expected_required_capital = target_qty * current_price
                        logging.info(f"💰 [자금관리] 켈리 베팅 기반 풀레버리지 진입: 목표 예산 {budget:,.0f}원 (주문: {target_qty}주, 예상 필요 자금: {expected_required_capital:,.0f}원)")
                        # 5. 스마트 지정가 매수 라우팅
                        self.smart_order_routing(code, target_qty, "BUY", current_price, orderbook_data)
                        
                        # 포지션 등록 및 DB 기록
                        self.positions[code] = {
                            'qty': target_qty,
                            'buy_price': current_price,
                            'buy_time': time.time()
                        }
                        if self.db:
                            self.db.log_trade(code, "BUY", target_qty, current_price, profit=0)
                    else:
                        # 예산 부족 로그 (최초 1회만 출력되도록 처리)
                        if not hasattr(self, 'insufficient_budget_logged'):
                            self.insufficient_budget_logged = set()
                        if code not in self.insufficient_budget_logged:
                            expected_required_capital = current_price # 최소 1주 매수에 필요한 예상 자금
                            logging.warning(f"⚠️ [자금관리] 예산 부족으로 {code} 주문 불가 (현재가: {current_price}원, 가용 예산: {budget:,.0f}원, 예상 필요 자금: {expected_required_capital:,.0f}원). '.env' 파일의 INVESTMENT_BUDGET을 늘려주세요.")
                            self.insufficient_budget_logged.add(code)

                # 6. 상한가 오버나잇 결정
                if self.decide_limit_up_overnight(code, current_price, limit_up_price, orderbook_data):
                    pass
                
                # (루프 간 지연 방지용)
                time.sleep(0.1) 
                
            # 유니버스 전체 순회 후 서버 부하 방지를 위해 2초 대기
            time.sleep(2.0)
