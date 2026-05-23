import sys
import os
import time
from datetime import datetime
import pandas as pd
import yaml
import logging

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

def load_config():
    load_dotenv()
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
        
    # 환경 변수에서 시크릿 값 로드 (config.yaml 덮어쓰기)
    if 'auth' not in config:
        config['auth'] = {}
        
    config['auth']['kis_app_key'] = os.getenv('KIS_APP_KEY', config['auth'].get('kis_app_key', ''))
    config['auth']['kis_app_secret'] = os.getenv('KIS_APP_SECRET', config['auth'].get('kis_app_secret', ''))
    config['auth']['kis_account_no'] = os.getenv('KIS_ACCOUNT_NO', config['auth'].get('kis_account_no', ''))
    config['auth']['kis_account_suffix'] = os.getenv('KIS_ACCOUNT_SUFFIX', config['auth'].get('kis_account_suffix', '01'))
    config['auth']['slack_bot_token'] = os.getenv('SLACK_BOT_TOKEN', config['auth'].get('slack_bot_token', ''))
    config['auth']['slack_channel_id'] = os.getenv('SLACK_CHANNEL_ID', config['auth'].get('slack_channel_id', ''))
    config['auth']['gemini_api_key'] = os.getenv('GEMINI_API_KEY', config['auth'].get('gemini_api_key', ''))
    
    return config

def main():
    config = load_config()
    
    # 1. 시스템 초기화
    print("🚀 Antigravity Quant Trader (KIS Edition) 시스템 시동 중...")
    db = TradeDatabase()
    notifier = SlackNotifier(config['auth']['slack_bot_token'], config['auth']['slack_channel_id'])
    
    # 2. KIS API 브로커 초기화 (Ubuntu 호환)
    broker = KISBroker(config)
    print("✅ KIS API 연결 및 계좌 정보 확인 완료")
    
    # 3. 전략 구성 및 분기
    universe = config['trading']['universe']
    
    # ⚡ 1,000% 달성을 위한 Extreme Growth 모드 확인
    if config.get('trading', {}).get('extreme_growth', {}).get('enable', False):
        print("⚡ [Extreme Growth] 1만원 -> 10만원 (1,000%) 달성 특화 모드로 진입합니다!")
        extreme_strategy = ExtremeGrowthStrategy(broker, universe, config)
        extreme_strategy.run()
        return # 해당 모드는 자체 무한 루프를 가지므로 메인 함수 종료
        
    strategies = {
        "Breakout": VolatilityBreakout(broker, universe),
        "MeanReversion": MeanReversion(broker, universe),
        "TrendFollowing": TrendFollowing(broker, universe)
    }
    ensemble = EnsembleEngine(strategies)
    
    # 4. 리스크 매니저 초기화
    risk_manager = MarketRiskManager(MacroCollector(), max_budget=config['trading']['max_budget'])
    
    # 5. 자동매매 메인 루프
    print("🔍 실시간 시장 감시 모드 진입 (Ubuntu Environment)")
    notifier.send_message("KIS 자동매매 시스템이 시작되었습니다.")
    
    try:
        while True:
            now = datetime.now()
            # 장중 시간 확인 (09:00 ~ 15:20)
            if now.hour >= 9 and (now.hour < 15 or (now.hour == 15 and now.minute <= 20)):
                # 글로벌 리스크 확인
                multiplier = risk_manager.get_trading_multiplier()
                
                if multiplier > 0:
                    for code in universe:
                        # 현재가 및 데이터 수집 (실제 구현 시 KIS API 활용 데이터프레임 생성 필요)
                        price = broker.get_price(code)
                        df = pd.DataFrame() # 데이터 수집 로직 (샘플)
                        
                        if ensemble.get_signals(code, df):
                            print(f"🎯 [{code}] 매수 조건 충족! 현재가: {price}")
                            # 주문 집행
                            # qty = int((config['trading']['max_budget'] * multiplier) / price)
                            # broker.send_order(code, qty, price, order_type="01")
                            # db.log_trade(...)
                            # notifier.notify_order(...)
                else:
                    logging.warning("⚠️ 글로벌 리스크 과다로 매매 일시 정지")
            else:
                if now.hour == 15 and now.minute > 30:
                    print("💤 장 종료. 시스템을 대기 모드로 전환합니다.")
                    time.sleep(3600)
            
            time.sleep(10) # API 호출 제한을 고려하여 주기 조정
    except KeyboardInterrupt:
        print("\n🛑 사용자에 의해 시스템이 중단되었습니다.")
    except Exception as e:
        logging.error(f"❌ 예기치 못한 오류 발생: {e}")
        notifier.send_message(f"🚨 시스템 오류 발생: {e}")

if __name__ == "__main__":
    main()
