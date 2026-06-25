import math

class DynamicLeverageManager:
    def __init__(self, initial_capital, max_margin_rate=2.5,
                 min_trades_for_kelly=5, min_trades_for_leverage=20,
                 cold_start_fraction=0.2):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.max_margin_rate = max_margin_rate # 최대 미수/신용 레버리지 배수

        # 표본 부족(콜드 스타트) 및 레버리지 허용을 가르는 임계 표본 수
        # - min_trades_for_kelly: 이 미만이면 켈리 대신 보수적 고정 비율 사용
        # - min_trades_for_leverage: 검증된 표본이 이만큼 쌓이기 전에는 미수/레버리지 절대 금지
        self.min_trades_for_kelly = min_trades_for_kelly
        self.min_trades_for_leverage = min_trades_for_leverage
        # 콜드 스타트 시 투입 비율(총자산 대비). 레버리지는 적용하지 않는다.
        self.cold_start_fraction = cold_start_fraction

        # 켈리 베팅을 위한 추적 데이터
        self.win_count = 0
        self.loss_count = 0
        self.total_win_rate = 0.0
        self.average_win_profit = 0.0
        self.average_loss_profit = 0.0

        self.trades = []

    def update_trade_result(self, is_win, profit_pct):
        """매매 결과 업데이트 (켈리 공식 계산용)"""
        self.trades.append((is_win, profit_pct))
        if is_win:
            self.win_count += 1
            # 간소화된 평균 수익률 계산
            self.average_win_profit = (self.average_win_profit * (self.win_count - 1) + profit_pct) / self.win_count
        else:
            self.loss_count += 1
            self.average_loss_profit = (self.average_loss_profit * (self.loss_count - 1) + abs(profit_pct)) / self.loss_count

        total_trades = self.win_count + self.loss_count
        self.total_win_rate = self.win_count / total_trades if total_trades > 0 else 0.0

    def _raw_kelly_fraction(self):
        """비용/표본 보정 전의 순수 켈리 비율(음수 가능). 기대값 판정용 내부 헬퍼."""
        # f* = W - ((1 - W) / R)
        # W: 승률, R: 손익비 (평균수익/평균손실)
        if self.average_loss_profit == 0:
            # 아직 손실 표본이 없으면 승리가 한 번이라도 있으면 양(+)으로 간주
            return 1.0 if self.win_count > 0 else 0.0
        reward_risk_ratio = self.average_win_profit / self.average_loss_profit
        if reward_risk_ratio == 0:
            return 0.0
        return self.total_win_rate - ((1 - self.total_win_rate) / reward_risk_ratio)

    def has_positive_edge(self):
        """충분한 표본에서 켈리 기대값이 양(+)인지(= 검증된 우위 존재) 판정.

        레버리지 사용 여부를 가르는 핵심 게이트. 표본이 부족하면 우위가
        '증명되지 않은' 것으로 보고 False를 반환한다.
        """
        if self.win_count + self.loss_count < self.min_trades_for_kelly:
            return False
        return self._raw_kelly_fraction() > 0

    def calculate_kelly_fraction(self):
        """켈리 베팅 비율 계산 (최적 투자 비중, 0~1)"""
        # 표본이 부족한 콜드 스타트 구간에서는 켈리를 신뢰할 수 없으므로
        # 보수적 고정 비율만 사용한다. (과거에는 0.5를 반환해 첫 거래부터
        # 레버리지 임계값(0.3)을 넘겨 미수 풀레버리지가 작동하는 결함이 있었다.)
        if self.win_count + self.loss_count < self.min_trades_for_kelly:
            return self.cold_start_fraction

        kelly_fraction = self._raw_kelly_fraction()
        if self.average_loss_profit == 0:
            # 손실 표본이 없을 때도 무한 신뢰(풀베팅)는 금물 — 절반으로 제한
            return 0.5

        # 하프 켈리 (안정성을 위해 켈리 비율의 절반만 사용)
        half_kelly = kelly_fraction / 2.0

        # 비중은 0% ~ 100% 사이로 제한
        return max(0.0, min(1.0, half_kelly))

    def get_optimal_budget(self, current_account_balance, use_margin=True):
        """현재 잔고와 켈리 비율을 기반으로 최적의 투입 자본 계산 (레버리지 포함)"""
        kelly_ratio = self.calculate_kelly_fraction()

        # 기본 투입 자본
        base_budget = current_account_balance * kelly_ratio

        # 미수/신용 레버리지는 다음 조건을 모두 만족할 때만 허용한다:
        #   1) 사용자가 명시적으로 활성화(use_margin)
        #   2) 검증에 충분한 표본 누적(min_trades_for_leverage 이상)
        #   3) 그 표본에서 기대값이 양(+) — 즉 실제로 검증된 우위 존재
        #   4) 켈리 비율이 충분히 높음(> 0.3)
        # 표본 없이 첫 거래부터 풀레버리지를 거는 파산 경로를 원천 차단한다.
        total_trades = self.win_count + self.loss_count
        if (use_margin
                and total_trades >= self.min_trades_for_leverage
                and self.has_positive_edge()
                and kelly_ratio > 0.3):
            # 보유 자금의 최대 max_margin_rate 배수까지 미수 베팅
            return base_budget * self.max_margin_rate

        return base_budget

    def enforce_margin_liquidation(self, current_time):
        """15:15 즈음 미수 동결 방지를 위한 강제 청산 신호 (오버나잇 예외 제외)"""
        # "15:15:00" 이후인지 확인
        if current_time >= "15:15:00":
            return True
        return False
