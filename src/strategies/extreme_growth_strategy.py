import numpy as np
import time
import logging
from .base_strategy import BaseStrategy
from core.leverage_manager import DynamicLeverageManager

class ExtremeGrowthStrategy(BaseStrategy):
    """
    1만원 -> 10만원 (1,000% 수익) 달성을 위한 극단적 초단기/고위험 스캘핑 전략
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

    def run(self):
        logging.info("🚀 [Extreme Growth 1,000% 목표 모드] 엔진 가동. 미수 풀레버리지/스캘핑 시스템 시작.")
        
        while True:
            current_time = time.strftime("%H:%M:%S")
            
            # 1. 15:15 미수 동결 방지 강제 청산 체크
            if self.leverage_manager.enforce_margin_liquidation(current_time):
                if not getattr(self, 'liquidation_triggered', False):
                    logging.warning("⚠️ [리스크 관리] 장 마감 임박. 미수 동결을 막기 위해 전 종목 강제 청산 (상한가 오버나잇 예외 제외)")
                    self.liquidation_triggered = True
                    # 보유한 모든 포지션 강제 청산
                    for code in list(self.positions.keys()):
                        self.sell_position(code, reason="장 마감 강제 청산")
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
                    
                # API를 통해 실시간 호가 및 현재가 수신 (Mock)
                current_price = 50000
                limit_up_price = 65000
                orderbook_data = {'trade_intensity': 250.0, 'ask_remains': 15000, 'bid_remains': 3000, 'limit_bid_remains': 1000000, 'total_volume': 5000000}
                current_news = [{'code': code, 'title': '초대형 무상증자 결정 공시'}] # (Mock)

                # 2. 뉴스 이벤트 드리븐 감지
                news_target = self.scan_event_driven_news(current_news)
                
                # 3. 마이크로 틱 스캘핑 호가창 돌파 감지
                is_breakout = self.analyze_micro_scalping_orderbook(code, orderbook_data)

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
                        logging.info(f"💰 [자금관리] 켈리 베팅 기반 풀레버리지 진입: 목표 예산 {budget:,.0f}원 (수량: {target_qty}주, 잔여 가용 원금: {available_capital:,.0f}원)")
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
                            logging.warning(f"⚠️ [자금관리] 예산 부족으로 {code} 주문 불가 (현재가: {current_price}원, 가용 예산: {budget:,.0f}원, 잔여 가용 원금: {available_capital:,.0f}원). '.env' 파일의 INVESTMENT_BUDGET을 늘려주세요.")
                            self.insufficient_budget_logged.add(code)

                # 6. 상한가 오버나잇 결정
                if self.decide_limit_up_overnight(code, current_price, limit_up_price, orderbook_data):
                    pass
                
                # (루프 간 지연 방지용)
                time.sleep(0.1) 
                
            # 유니버스 전체 순회 후 서버 부하 방지를 위해 2초 대기
            time.sleep(2.0)
