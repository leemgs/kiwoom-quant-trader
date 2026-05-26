class MarketRiskManager:
    def __init__(self, macro_collector, max_trading_limit=None, db=None):
        self.collector = macro_collector
        self.max_trading_limit = max_trading_limit
        self.db = db
        self.risk_score = 0 # 0(안전) ~ 100(위험)

    def calculate_risk_index(self):
        """글로벌 지수를 종합하여 리스크 점수 산출"""
        status = self.collector.get_market_status()
        if not status:
            return 50 # 정보 부재 시 중립

        score = 50
        # 1. 나스닥/S&P500 영향 (하락 시 위험 증가)
        us_market_change = (status['Nasdaq'] + status['S&P500']) / 2
        score -= us_market_change * 10 # 1% 하락 시 점수 10점 증가

        # 2. 환율 영향 (상승 시 위험 증가)
        fx_change = status['USD/KRW']
        score += fx_change * 20 # 환율 1% 상승 시 점수 20점 증가

        self.risk_score = max(0, min(100, score))
        return self.risk_score

    def get_trading_multiplier(self, current_investment=0):
        """리스크 점수 및 투자 한도에 따른 매매 비중 반환"""
        self.calculate_risk_index()
        
        # 1. 투자 한도(max_trading_limit) 체크 (실현 손익을 반영한 동적 한도 계산)
        allowed_limit = self.max_trading_limit
        if self.db:
            total_profit = self.db.get_total_profit()
            allowed_limit = max(0.0, self.max_trading_limit + total_profit)
            
        if allowed_limit and current_investment >= allowed_limit:
            print(f"🛑 [RiskManager] 설정된 투자 한도({allowed_limit:,.0f}원) 초과 (현재 투자액: {current_investment:,.0f}원). 매매를 중단합니다.")
            return 0.0

        if self.risk_score >= 80: # 극도로 위험
            return 0.0 # 매매 중단
        elif self.risk_score >= 60: # 주의
            return 0.5 # 비중 50% 축소
        elif self.risk_score <= 30: # 매우 안전 (상승장)
            return 1.2 # 비중 20% 확대 (공격적 매매)
        else:
            return 1.0 # 정상 비중
