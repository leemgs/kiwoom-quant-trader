import sys
import os
import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone, timedelta
import holidays
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# sys.path 설정: src 폴더를 포함하여 analytics 등을 임포트 가능하도록 함
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# 페이지 설정
st.set_page_config(page_title="Real-time Dashboard for Stock Quant Trader", layout="wide")

# 사이드바 상단 여백을 극대화하여 줄여 상단으로 요소를 끌어올림
st.markdown(
    """
    <style>
        [data-testid="stSidebarUserContent"] {
            padding-top: 1.5rem !important;
        }
    </style>
    """,
    unsafe_allow_html=True
)

def get_data():
    try:
        is_virtual = os.getenv('KIS_VIRTUAL_TRADING', 'true').lower() == 'true'
        db_path = "data/trading_history_mock.db" if is_virtual else "data/trading_history_real.db"
        conn = sqlite3.connect(db_path)
        df = pd.read_sql("SELECT * FROM trades ORDER BY timestamp DESC", conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=10)
def get_account_balance():
    try:
        from broker.kis_api import KISBroker
        
        config = {
            'auth': {
                "kis_app_key": os.getenv('KIS_APP_KEY', ''),
                "kis_app_secret": os.getenv('KIS_APP_SECRET', ''),
                "kis_account_no": os.getenv('KIS_ACCOUNT_NO', ''),
                "kis_account_suffix": os.getenv('KIS_ACCOUNT_SUFFIX', '01'),
                "kis_virtual_trading": os.getenv('KIS_VIRTUAL_TRADING', 'true').lower() == 'true',
            }
        }
        
        if not config['auth']['kis_app_key'] or not config['auth']['kis_app_secret']:
            return "설정 필요"
            
        broker = KISBroker(config)
        res = broker.api.fetch_balance()
        
        if isinstance(res, dict) and ('output2' in res or res.get('rt_cd') == '0'):
            output2 = res.get('output2', [])
            if output2:
                cash = int(output2[0].get('dnca_tot_amt', 0))
                total_assets = int(output2[0].get('tot_evlu_amt', cash))
                return {
                    'cash': cash,
                    'total_assets': total_assets
                }
        else:
            msg = res.get('msg1', '조회 실패') if isinstance(res, dict) else '응답 오류'
            return f"오류 ({msg})"
        return None
    except Exception as e:
        print(f"Error fetching account balance: {e}")
        return f"에러 ({str(e)})"

from dotenv import load_dotenv

load_dotenv()
kis_account_no = os.getenv('KIS_ACCOUNT_NO', 'Unknown')
kis_account_suffix = os.getenv('KIS_ACCOUNT_SUFFIX', '01')
investment_budget = int(os.getenv('INVESTMENT_BUDGET', '10000'))

BASELINE_FILE = "data/profit_baseline.txt"

def get_profit_baseline(default_value):
    if os.path.exists(BASELINE_FILE):
        try:
            with open(BASELINE_FILE, "r") as f:
                return float(f.read().strip())
        except:
            pass
    return default_value

def save_profit_baseline(value):
    try:
        os.makedirs(os.path.dirname(BASELINE_FILE), exist_ok=True)
        with open(BASELINE_FILE, "w") as f:
            f.write(str(value))
    except Exception as e:
        print(f"Error saving profit baseline: {e}")

# ---------------------------------------------------
# Holiday & market status utilities
# ---------------------------------------------------
kst = timezone(timedelta(hours=9))
now = datetime.now(kst)
today = now.date()

# Korean holidays (including substitute holidays)
kr_holidays = holidays.CountryHoliday('KR')
is_kor_holiday = today in kr_holidays

# US market holidays (NYSE calendar)
us_holidays = holidays.CountryHoliday('US')
is_us_holiday = today in us_holidays

# Determine if each market is tradable now
# Korean market trading window (same as before)
is_kor_trading = not is_kor_holiday and now.weekday() < 5 and (
    (now.hour == 8 and now.minute >= 50) or
    (now.hour >= 9 and now.hour < 15) or
    (now.hour == 15 and now.minute <= 20)
)
# US market trading window (NYSE 09:30-16:00 ET, which is 22:30-05:00 KST next day)
# For simplicity we only check if today is a weekday and not a US holiday.
# US market trading window (NY time: 09:30‑16:00 ET, which is 22:30‑05:00 KST next day)
# Convert current KST to US Eastern Time (EDT)
us_tz = timezone(timedelta(hours=-4))
now_us = datetime.now(us_tz)
# US market is open if it's a weekday, not a US holiday, and within ET trading hours
is_us_trading = (
    not is_us_holiday and
    now_us.weekday() < 5 and
    (
        now_us.hour > 9 or
        (now_us.hour == 9 and now_us.minute >= 30)
    ) and
    (now_us.hour < 16 or (now_us.hour == 16 and now_us.minute == 0))
)

is_virtual = os.getenv('KIS_VIRTUAL_TRADING', 'true').lower() == 'true'

# 데이터 로드 및 현재 자산 계산
df = get_data()
total_profit = df['profit'].sum() if not df.empty else 0
current_total = investment_budget + total_profit

# KIS API를 통해 실시간 계좌 예수금 및 총자산 조회
balance_info = get_account_balance()
real_total_assets = investment_budget
real_cash = 0
account_balance_str = "조회 실패"

if isinstance(balance_info, dict):
    real_cash = balance_info['cash']
    real_total_assets = balance_info['total_assets']
    account_balance_str = f"{real_cash:,}원"
elif isinstance(balance_info, str):
    account_balance_str = balance_info
    real_total_assets = current_total
else:
    account_balance_str = "조회 실패"
    real_total_assets = current_total

# 실현손익 계산: 모의 투자면 DB 기록을 그대로 표기하고, 실전 투자면 실제 자산 증감액(실제 총자산 - 기준액)만 산출
if is_virtual:
    system_profit = total_profit
    system_profit_label = "시스템 누적 실현손익 (모의)"
else:
    baseline = get_profit_baseline(investment_budget)
    system_profit = real_total_assets - baseline
    system_profit_label = "시스템 누적 실현손익 (실전)"

# ---------------------------------------------------
# Sidebar: auto‑trading status with per‑country flags
# ---------------------------------------------------
status_bg = "#e8f5e9" if is_kor_trading else "#f5f5f5"
status_color = "#2e7d32" if is_kor_trading else "#555555"
is_any_trading = is_kor_trading or is_us_trading

trading_type_str = "모의" if is_virtual else "실전"
trading_type_color = "#2e7d32" if is_virtual else "#e53935"

# 사이드바 설정
st.sidebar.markdown(
    f"""
<div style='background-color: #ffffff; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 15px; border: 1px solid #e0e0e0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);'>
<h3 style='color: #03256C; margin: 0 0 3px 0; font-weight: 900; letter-spacing: 1px;'>한국투자증권</h3>
<p style='color: #666; font-size: 11px; margin: 0 0 10px 0; font-weight: 600;'>KOREA INVESTMENT & SECURITIES</p>
<a href='https://apiportal.koreainvestment.com/' target='_blank' style='text-decoration: none;'>
<div style='background-color: #03256C; color: white; padding: 6px 10px; border-radius: 6px; font-size: 12px; font-weight: bold;'>
🚀 KIS Developers (Open API)
</div>
</a>
</div>

<div style="margin-bottom: 10px;">
<h4 style="margin: 0 0 8px 0; font-size: 16px;">💎 Trading Bot Control</h4>
<div style="background-color: {status_bg}; padding: 8px; border-radius: 5px; color: {status_color}; font-size: 13px; font-weight: bold; margin-bottom: 10px; line-height: 1.5;">
시스템 상태: 🟢 가동 중<br>
자동매매 상태: {'⚔️ 전투 중' if is_any_trading else '💤 휴식 중'} (한국:{'O' if not is_kor_holiday else 'X'}, 미국:{'O' if not is_us_holiday else 'X'})
</div>
<p style="margin: 0 0 5px 0; font-size: 13px;"><strong>KIS Account:</strong> <code>{kis_account_no}-{kis_account_suffix}</code></p>
<p style="margin: 0 0 5px 0; font-size: 13px;"><strong>투자 운영 종류:</strong> <code style="color: {trading_type_color}; font-weight: bold;">{trading_type_str}</code></p>
<p style="margin: 0 0 5px 0; font-size: 13px;"><strong>투자 운영 금액 (원금):</strong> <code>{investment_budget:,}원</code></p>
<p style="margin: 0 0 5px 0; font-size: 13px;"><strong>투자 운영 결과 (실제 총자산):</strong> <code style="color: {'#e53935' if real_total_assets < investment_budget else '#2e7d32' if real_total_assets > investment_budget else '#333'}; font-weight: bold;">{real_total_assets:,}원</code></p>
<p style="margin: 0 0 5px 0; font-size: 13px;"><strong>증권 계좌 예수금 (현금):</strong> <code style="font-weight: bold;">{account_balance_str}</code></p>
<p style="margin: 0 0 15px 0; font-size: 13px;"><strong>{system_profit_label}:</strong> <code style="color: {'#e53935' if system_profit < 0 else '#2e7d32' if system_profit > 0 else '#333'}; font-weight: bold;">{system_profit:+,}원</code></p>
</div>
""",
    unsafe_allow_html=True
)

# 실전 모드일 때만 실손익 초기화 기능 제공
if not is_virtual:
    if 'show_reset_confirm' not in st.session_state:
        st.session_state['show_reset_confirm'] = False

    if not st.session_state['show_reset_confirm']:
        if st.sidebar.button("실전 손익 초기화 🔄", help="현재 실제 총자산을 기준으로 누적 실현손익을 0원으로 리셋합니다."):
            st.session_state['show_reset_confirm'] = True
            st.rerun()
    else:
        st.sidebar.warning("기존 실현 손익액이 0원으로 완전히 초기화됩니다. 정말 수행하시겠습니까?")
        col1, col2 = st.sidebar.columns(2)
        with col1:
            if st.button("예", use_container_width=True):
                save_profit_baseline(real_total_assets)
                # 실전 거래 내역 데이터베이스의 거래 기록 삭제
                try:
                    from core.database import TradeDatabase
                    db = TradeDatabase("data/trading_history_real.db")
                    with sqlite3.connect(db.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM trades")
                        conn.commit()
                except Exception as e:
                    print(f"Error clearing real trades DB: {e}")
                st.session_state['show_reset_confirm'] = False
                st.sidebar.success("초기화 완료!")
                st.rerun()
        with col2:
            if st.button("아니오", use_container_width=True):
                st.session_state['show_reset_confirm'] = False
                st.rerun()

# ---------------------------------------------------
# Expander for trading‑hours with holiday info and info icon
# ---------------------------------------------------
expander_title = f"⏰ {now.strftime('%Y-%m-%d %H:%M')} (한국:{'휴일' if is_kor_holiday else '평일'}, 미국:{'휴일' if is_us_holiday else '평일'}) ℹ️"
with st.sidebar.expander(expander_title):
    st.markdown("""
<table style="width: 100%; border-collapse: collapse; font-size: 11.5px; margin-top: 5px; border: 1px solid #e0e0e0; border-radius: 6px;">
  <thead>
    <tr style="border-bottom: 2px solid #e0e0e0; background-color: #f8f9fa;">
      <th style="text-align: left; padding: 6px; font-weight: bold; color: #333;">구분</th>
      <th style="text-align: center; padding: 6px; font-weight: bold; color: #03256C;">한국</th>
      <th style="text-align: center; padding: 6px; font-weight: bold; color: #a53535;">미국</th>
    </tr>
  </thead>
  <tbody>
    <tr style="border-bottom: 1px solid #eee;">
      <td style="padding: 6px; font-weight: bold; color: #555; background-color: #fafafa;">운영 요일</td>
      <td style="text-align: center; padding: 6px; color: #333;">월 ~ 금<br><span style="font-size:9.5px; color:#888;">(공휴일 제외)</span></td>
      <td style="text-align: center; padding: 6px; color: #333;">월 ~ 금<br><span style="font-size:9.5px; color:#888;">(공휴일 제외)</span></td>
    </tr>
    <tr style="border-bottom: 1px solid #eee;">
      <td style="padding: 6px; font-weight: bold; color: #555; background-color: #fafafa;">개장 준비</td>
      <td style="text-align: center; padding: 6px; color: #333;">08:50 ~ 09:00</td>
      <td style="text-align: center; padding: 6px; color: #333;">22:30 ~ 23:30</td>
    </tr>
    <tr style="border-bottom: 1px solid #eee;">
      <td style="padding: 6px; font-weight: bold; color: #555; background-color: #fafafa;">자동 매매</td>
      <td style="text-align: center; padding: 6px; color: #2e7d32; font-weight: bold;">09:00 ~ 15:15</td>
      <td style="text-align: center; padding: 6px; color: #c62828; font-weight: bold;">23:30 ~ 05:00</td>
    </tr>
    <tr>
      <td style="padding: 6px; font-weight: bold; color: #555; background-color: #fafafa;">강제 청산</td>
      <td style="text-align: center; padding: 6px; color: #e53935; font-weight: bold;">15:15<br><span style="font-size:9.5px; font-weight:normal; color:#e53935;">(미수 방지)</span></td>
      <td style="text-align: center; padding: 6px; color: #777;">-</td>
    </tr>
  </tbody>
</table>
""", unsafe_allow_html=True)

refresh_rate = st.sidebar.slider("새로고침 간격(초)", 5, 60, 10)

st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    <a href="https://leemgs.github.io/stock-quant-trader-kis/" target="_blank" style="text-decoration: none;">
        <div style='background-color: #f8f9fa; color: #333; padding: 10px; border-radius: 6px; text-align: center; border: 1px solid #ddd; font-weight: bold; font-size: 14px; transition: 0.2s;'>
            🏠 프로젝트 공식 홈페이지
        </div>
    </a>
    """,
    unsafe_allow_html=True
)

# 메인 타이틀
st.markdown("<h2 style='font-size: 28px; font-weight: bold; margin-bottom: 20px;'>🚀 Real-time Dashboard for Stock Quant Trader</h2>", unsafe_allow_html=True)

# 목표 설정 (환경 변수 동적 반영)
INITIAL_SEED = investment_budget
INVESTMENT_PERIOD_MONTH = int(os.getenv('INVESTMENT_PERIOD_MONTH', '1'))
INVESTMENT_INCOME_GOAL = float(os.getenv('INVESTMENT_INCOME_GOAL', '100000'))
TARGET_GOAL = INVESTMENT_INCOME_GOAL

# 1. 상단 메트릭 (총 수익, 승률 등) 및 챌린지 현황판
col1, col2, col3, col4 = st.columns(4)

if not is_virtual:
    # 실전 투자의 경우:
    # 누적 손익은 system_profit (실제 총자산 - baseline)
    # 현재 총 자산은 실제 총자산 (real_total_assets)
    display_profit = system_profit
    display_current_total = real_total_assets
else:
    # 모의 투자의 경우:
    # 누적 손익은 DB 거래 내역의 합
    # 현재 총 자산은 시작 자산 + 누적 손익
    display_profit = df['profit'].sum() if not df.empty else 0.0
    display_current_total = INITIAL_SEED + display_profit

if not df.empty:
    total_trades = len(df)
    win_rate = (df['profit'] > 0).mean() * 100
else:
    total_trades = 0
    win_rate = 0.0

col1.metric("총 거래 횟수", f"{total_trades}회")
col2.metric("승률", f"{win_rate:.1f}%")
col3.metric("누적 손익", f"{display_profit:,.0f}원", delta=f"{display_profit:,.0f}")
col4.metric("목표 달성률", f"{(display_profit/TARGET_GOAL)*100:.1f}%")

# 1.5 챌린지 현황판
st.divider()
st.subheader(f"🎯 {INVESTMENT_PERIOD_MONTH}개월 수익 도전 ({INITIAL_SEED:,}원 → {TARGET_GOAL:,}원)")
progress = min(1.0, max(0.0, display_current_total / TARGET_GOAL))
st.progress(progress)
st.write(f"현재 총 자산: **{display_current_total:,.0f}원** / 목표 자산: **{TARGET_GOAL:,.0f}원**")

# 2. 실시간 수익률 곡선 및 상세 정보
if not df.empty:
    st.subheader("📈 Cumulative Equity Curve")
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp')
    df['cum_profit'] = df['profit'].cumsum()
    
    # pandas Timestamp subclass can trigger RecursionError in Plotly on Python 3.9.
    # We convert to string format for plotting to bypass the typing check safely.
    plot_df = df.copy()
    plot_df['timestamp'] = plot_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
    
    fig_curve = px.line(plot_df, x='timestamp', y='cum_profit', title='누적 수익률 추이')
    st.plotly_chart(fig_curve, use_container_width=True)

    # 3. 현재 보유 종목 및 매매 히스토리
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("📋 Recent Trade History")
        st.dataframe(df.sort_values('timestamp', ascending=False).head(10), use_container_width=True)
        
    with col_right:
        st.subheader("🔥 Profit/Loss Heatmap")
        # 종목별 누적 수익 계산 (Plotly treemap은 음수나 합계 0일 때 크기 계산 오류 방지 위해 절대값 사용)
        df_group = df.groupby('code').agg({'profit': 'sum'}).reset_index()
        df_group['abs_profit'] = df_group['profit'].abs()
        if df_group['abs_profit'].sum() == 0:
            df_group['abs_profit'] = 1.0  # ZeroDivisionError 방지
            
        fig_heat = px.treemap(df_group, path=['code'], values='abs_profit', color='profit',
                             color_continuous_scale='RdYlGn', title='종목별 수익 기여도',
                             hover_data=['profit'])
        st.plotly_chart(fig_heat, use_container_width=True)

    # 4. AI 투자 복기 섹션
    st.divider()
    st.subheader("🤖 Gemini AI Investment Insights")
    if st.button("AI 매매 복기 생성"):
        from analytics.ai_journal import AITradingJournal
        api_key = os.getenv("GEMINI_API_KEY", "") 
        journal = AITradingJournal(api_key)
        
        with st.spinner("AI가 오늘의 매매를 분석 중입니다..."):
            # 실제 구현 시 macro_status 데이터 전달 필요
            review = journal.generate_review(df, "Nasdaq: +1.2%, USD/KRW: -0.5%")
            st.info(review)
else:
    st.warning("아직 거래 내역이 없습니다. 시스템이 거래를 시작하면 차트와 상세 내역이 활성화됩니다.")

# ---------------------------------------------------
# System Activity Logs (실시간 시스템 로그)
# ---------------------------------------------------
st.divider()
st.subheader("🤖 System Activity Logs (실시간 시스템 로그)")

def get_recent_logs(log_path="logs/trading.log", num_lines=30):
    if not os.path.exists(log_path):
        return ["로그 파일이 존재하지 않습니다."]
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            lines = [line.strip() for line in lines if line.strip()]
            return lines[-num_lines:]
    except Exception as e:
        return [f"로그를 읽는 중 오류가 발생했습니다: {str(e)}"]

def format_logs_to_html(logs):
    formatted_lines = []
    # 최신 로그가 위에 오도록 역순 배치
    for line in reversed(logs):
        escaped_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        # 레벨별 색상 설정
        if " - INFO - " in escaped_line:
            if any(emoji in escaped_line for emoji in ["🔥", "🚀", "🎯", "✅", "⚡", "💎"]):
                color = "#4fc3f7" # 하늘색 (주요 정보)
            else:
                color = "#e0e0e0" # 연한 회색 (일반 정보)
        elif " - WARNING - " in escaped_line or "⚠️" in escaped_line:
            color = "#ffb74d" # 주황색 (경고)
        elif " - ERROR - " in escaped_line or "❌" in escaped_line or "🚨" in escaped_line:
            color = "#e57373" # 빨간색 (에러)
        else:
            color = "#f5f5f5"
            
        formatted_lines.append(f'<div style="color: {color}; margin-bottom: 4px; border-bottom: 1px solid #2d2d2d; padding-bottom: 4px; font-family: monospace; font-size: 13px;">{escaped_line}</div>')
    return "".join(formatted_lines)

log_lines = get_recent_logs()
formatted_html = format_logs_to_html(log_lines)

log_box_html = f"""
<div style="
    background-color: #1e1e1e;
    padding: 15px;
    border-radius: 8px;
    height: 350px;
    overflow-y: auto;
    border: 1px solid #333;
    box-shadow: inset 0 0 10px rgba(0,0,0,0.5);
">
    {formatted_html}
</div>
<p style="font-size: 11px; color: #888; margin-top: 5px; text-align: right;">※ 최신 로그가 상단에 표시됩니다. (새로고침 간격: {refresh_rate}초)</p>
"""
st.markdown(log_box_html, unsafe_allow_html=True)

# 자동 새로고침 설정 (Streamlit 1.27.0+ 기준)
import time
time.sleep(refresh_rate)
st.rerun()

