import sys
import os
import time
from datetime import datetime, timezone, timedelta
import pandas as pd

import logging
import holidays

# src 디렉토리를 path에 추가하여 모듈 임포트 지원
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from broker.kis_api import KISBroker
from core.ensemble_engine import EnsembleEngine
from core.notifier import SlackNotifier
from core.database import TradeDatabase
from core.risk_manager import MarketRiskManager
from core.macro_collector import MacroCollector
from strategies.volatility_breakout import VolatilityBreakout
from strategies.mean_reversion import MeanReversion
from strategies.trend_following import TrendFollowing
from strategies.extreme_growth_strategy import ExtremeGrowthStrategy

# 로깅 설정
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/trading.log"),
        logging.StreamHandler()
    ]
)

from dotenv import load_dotenv

def load_config() -> dict:
    """Load all configuration from environment variables.
    This completely removes the need for `config.yaml`.
    Values default to the same ones used previously.
    """
    load_dotenv()
    # Auth section – already loaded via dotenv
    auth = {
        "kis_app_key": os.getenv('KIS_APP_KEY', ''),
        "kis_app_secret": os.getenv('KIS_APP_SECRET', ''),
        "kis_account_no": os.getenv('KIS_ACCOUNT_NO', ''),
        "kis_account_suffix": os.getenv('KIS_ACCOUNT_SUFFIX', '01'),
        "kis_virtual_trading": os.getenv('KIS_VIRTUAL_TRADING', 'true').lower() == 'true',
        "slack_bot_token": os.getenv('SLACK_BOT_TOKEN', ''),
        "slack_channel_id": os.getenv('SLACK_CHANNEL_ID', ''),
        "gemini_api_key": os.getenv('GEMINI_API_KEY', ''),
    }

    # Helper to split comma‑separated values
    def csv_to_list(val: str) -> list:
        return [s.strip() for s in val.split(',') if s.strip()]

    # Trading section – parse CSV env vars and numeric defaults
    trading = {
        "universe": csv_to_list(os.getenv('UNIVERSE', '005930,000660,035420,035720')),
        "us_universe": csv_to_list(os.getenv('US_UNIVERSE', 'AAPL.US,MSFT.US,GOOGL.US')),
        "investment_budget": int(os.getenv('INVESTMENT_BUDGET', '10000')),
        "max_trading_limit": int(os.getenv('MAX_TRADING_LIMIT', '100000')),
        "k_value": float(os.getenv('K_VALUE', '0.4')),
        "stop_loss": float(os.getenv('STOP_LOSS', '0.015')),
        "take_profit": float(os.getenv('TAKE_PROFIT', '0.03')),
        "max_stocks": int(os.getenv('MAX_STOCKS', '1')),
        "extreme_growth": {
            "enable": os.getenv('EXTREME_GROWTH_ENABLE', 'true').lower() == 'true',
            "use_margin_leverage": os.getenv('EXTREME_GROWTH_USE_MARGIN', 'true').lower() == 'true',
            "smart_order_routing": os.getenv('EXTREME_GROWTH_SMART_ORDER', 'true').lower() == 'true',
            "micro_scalping_ticks": int(os.getenv('EXTREME_GROWTH_MICRO_SCALPING', '3')),
            "limit_up_overnight": os.getenv('EXTREME_GROWTH_LIMIT_UP', 'true').lower() == 'true',
            "kelly_criterion": os.getenv('EXTREME_GROWTH_KELLY', 'true').lower() == 'true',
        },
    }

    # Logging configuration (optional overrides via env)
    logging_cfg = {
        "level": os.getenv('LOG_LEVEL', 'INFO'),
        "file": os.getenv('LOG_FILE', 'logs/trading.log'),
    }

    return {
        "auth": auth,
        "trading": trading,
        "logging": logging_cfg,
    }

def main():
    config = load_config()
    
    # 1. 시스템 초기화
    print("🚀 Antigravity Quant Trader (KIS Edition) 시스템 시동 중...")
    is_virtual = config['auth']['kis_virtual_trading']
    db_path = "data/trading_history_mock.db" if is_virtual else "data/trading_history_real.db"
    db = TradeDatabase(db_path=db_path)
    notifier = SlackNotifier(config['auth']['slack_bot_token'], config['auth']['slack_channel_id'])
    
    # 2. KIS API 브로커 초기화 (Ubuntu 호환)
    broker = KISBroker(config)
    print("✅ KIS API 연결 및 계좌 정보 확인 완료")
    
    # 3. 전략 구성 및 분기
    universe = config['trading']['universe']
    
    # ⚡ 1,000% 달성을 위한 Extreme Growth 모드 확인
    if config.get('trading', {}).get('extreme_growth', {}).get('enable', False):
        budget = config.get('trading', {}).get('investment_budget', 20000)
        period = int(os.getenv('INVESTMENT_PERIOD_MONTH', '1'))
        goal = float(os.getenv('INVESTMENT_INCOME_GOAL', '100000'))
        print(f"⚡ [Extreme Growth] {budget:,}원으로 {period}개월 운영 후 {goal:,}원의 수익을 목표로 하는 특화 모드로 진입합니다!")
        extreme_strategy = ExtremeGrowthStrategy(broker, universe, config, db=db)
        extreme_strategy.run()
        return # 해당 모드는 자체 무한 루프를 가지므로 메인 함수 종료
        
    strategies = {
        "Breakout": VolatilityBreakout(broker, universe),
        "MeanReversion": MeanReversion(broker, universe),
        "TrendFollowing": TrendFollowing(broker, universe)
    }
    ensemble = EnsembleEngine(strategies)
    
    # 4. 리스크 매니저 초기화
    risk_manager = MarketRiskManager(
        MacroCollector(),
        investment_budget=config['trading']['investment_budget'],
        max_trading_limit=config['trading']['max_trading_limit'],
        db=db
    )
    
    # 5. 자동매매 메인 루프
    print("🔍 실시간 시장 감시 모드 진입 (Ubuntu Environment)")
    notifier.send_message("KIS 자동매매 시스템이 시작되었습니다.")
    
    try:
        while True:
            now = datetime.now()
            # 현재 KST 기준으로 한국·미국 공휴일 및 거래 가능 여부 확인
            kst = timezone(timedelta(hours=9))
            today = datetime.now(kst).date()
            kr_holidays = holidays.CountryHoliday('KR')
            us_holidays = holidays.CountryHoliday('US')
            is_kor_holiday = today in kr_holidays
            is_us_holiday = today in us_holidays
            # 한국 시장 트레이딩 가능 여부 (09:00~15:20 KST)
            is_kor_trading = (not is_kor_holiday and now.weekday() < 5 and (
                (now.hour == 8 and now.minute >= 50) or
                (now.hour >= 9 and now.hour < 15) or
                (now.hour == 15 and now.minute <= 20)
            ))
            # 미국 시장 트레이딩 가능 여부 (NY시간 09:30‑16:00 ET, KST와 변환)
            us_tz = timezone(timedelta(hours=-4))  # EDT (UTC‑4) 현재 시점
            now_us = datetime.now(us_tz)
            # 거래시간: 09:30 ≤ now_us < 16:00 (정규장) 및 평일·공휴일 제외
            is_us_trading = (
                not is_us_holiday and
                now_us.weekday() < 5 and
                (now_us.hour > 9 or (now_us.hour == 9 and now_us.minute >= 30)) and
                (now_us.hour < 16 or (now_us.hour == 16 and now_us.minute == 0))
            )
            # 어느 시장도 열려 있지 않다면 자동 매매 일시 정지
            if not (is_kor_trading or is_us_trading):
                logging.info("📅 오늘은 한국·미국 모두 휴일이거나 거래 시간이 아닙니다. 자동매매를 일시 정지합니다.")
                time.sleep(300)
                continue
            # 활성화된 시장에 맞는 티커 리스트 구성
            active_universe = []
            if is_kor_trading:
                active_universe.extend(universe)  # KR 티커
            if is_us_trading:
                us_universe = config.get('trading', {}).get('us_universe', ['AAPL.US', 'MSFT.US', 'GOOGL.US'])
                active_universe.extend(us_universe)
            # 글로벌 리스크 확인
            multiplier = risk_manager.get_trading_multiplier()
            if multiplier > 0:
                for code in active_universe:
                    price = broker.get_price(code)
                    df = pd.DataFrame()  # 실제 데이터 수집 로직은 추후 구현
                    if ensemble.get_signals(code, df):
                        print(f"🎯 [{code}] 매수 조건 충족! 현재가: {price}")
                        # 주문 로직 (주석 처리)
                        # qty = int((config['trading']['max_trading_limit'] * multiplier) / price)
                        # broker.send_order(code, qty, price, order_type="01")
                        # db.log_trade(...)
                        # notifier.notify_order(...)
            else:
                logging.warning("⚠️ 글로벌 리스크 과다로 매매 일시 정지")
            # 한국 장 종료 후 대기 처리
            if now.hour == 15 and now.minute > 30:
                print("💤 장 종료. 시스템을 대기 모드로 전환합니다.")
                time.sleep(3600)
            time.sleep(10)  # API 호출 제한을 고려하여 주기 조정
    except KeyboardInterrupt:
        print("\n🛑 사용자에 의해 시스템이 중단되었습니다.")
    except Exception as e:
        logging.error(f"❌ 예기치 못한 오류 발생: {e}")
        notifier.send_message(f"🚨 시스템 오류 발생: {e}")

if __name__ == "__main__":
    main()
