import sys
import os
import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# sys.path 설정: src 폴더를 포함하여 analytics 등을 임포트 가능하도록 함
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# 페이지 설정
st.set_page_config(page_title="Real-time Dashboard for Stock Quant Trader", layout="wide")

def get_data():
    try:
        conn = sqlite3.connect("data/trading_history.db")
        df = pd.read_sql("SELECT * FROM trades ORDER BY timestamp DESC", conn)
        conn.close()
        return df
    except:
        return pd.DataFrame()

from dotenv import load_dotenv

load_dotenv()
kis_account_no = os.getenv('KIS_ACCOUNT_NO', 'Unknown')
kis_account_suffix = os.getenv('KIS_ACCOUNT_SUFFIX', '01')
investment_budget = int(os.getenv('INVESTMENT_BUDGET', '10000'))

# 사이드바 설정
st.sidebar.markdown(
    """
    <div style='background-color: #ffffff; padding: 15px; border-radius: 10px; text-align: center; margin-bottom: 20px; border: 1px solid #e0e0e0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);'>
        <h3 style='color: #03256C; margin-top: 0px; margin-bottom: 5px; font-weight: 900; letter-spacing: 1px;'>한국투자증권</h3>
        <p style='color: #666; font-size: 11px; margin-bottom: 12px; font-weight: 600;'>KOREA INVESTMENT & SECURITIES</p>
        <a href='https://apiportal.koreainvestment.com/' target='_blank' style='text-decoration: none;'>
            <div style='background-color: #03256C; color: white; padding: 8px 10px; border-radius: 6px; font-size: 13px; font-weight: bold; transition: 0.3s;'>
                🚀 KIS Developers (Open API)
            </div>
        </a>
    </div>
    """,
    unsafe_allow_html=True
)

st.sidebar.title("💎 Trading Bot Control")
st.sidebar.info("시스템 상태: 🟢 가동 중")
st.sidebar.write(f"**KIS Account:** `{kis_account_no}-{kis_account_suffix}`")
st.sidebar.write(f"**투자 운영 금액:** `{investment_budget:,}원`")
st.sidebar.markdown("---")
st.sidebar.subheader("⏰ 매매 운영 시간")
st.sidebar.markdown("""
- **운영 요일**: 월 ~ 금 (공휴일 제외)
- **개장 준비**: 08:50 ~ 09:00
- **자동 매매**: 09:00 ~ 15:15
- **강제 청산**: 15:15 (미수 방지)
""")
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

# 데이터 로드
df = get_data()

# 목표 설정 (초기 자본금 -> 1,000% 수익 도전)
INITIAL_SEED = investment_budget
TARGET_GOAL = INITIAL_SEED * 10

if not df.empty:
    # 1. 상단 메트릭 (총 수익, 승률 등)
    col1, col2, col3, col4 = st.columns(4)
    total_trades = len(df)
    win_rate = (df['profit'] > 0).mean() * 100
    total_profit = df['profit'].sum()
    
    col1.metric("총 거래 횟수", f"{total_trades}회")
    col2.metric("승률", f"{win_rate:.1f}%")
    col3.metric("누적 손익", f"{total_profit:,.0f}원", delta=f"{total_profit:,.0f}")
    col4.metric("목표 달성률", f"{(total_profit/TARGET_GOAL)*100:.1f}%")

    # 1.5 챌린지 현황판
    st.divider()
    st.subheader(f"🎯 1,000% 수익 도전 ({INITIAL_SEED:,}원 → {TARGET_GOAL:,}원)")
    current_total = INITIAL_SEED + total_profit
    progress = min(1.0, current_total / TARGET_GOAL)
    st.progress(progress)
    st.write(f"현재 총 자산: **{current_total:,.0f}원** / 목표 자산: **{TARGET_GOAL:,.0f}원**")

    # 2. 실시간 수익률 곡선
    st.subheader("📈 Cumulative Equity Curve")
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp')
    df['cum_profit'] = df['profit'].cumsum()
    
    fig_curve = px.line(df, x='timestamp', y='cum_profit', title='누적 수익률 추이')
    st.plotly_chart(fig_curve, use_container_width=True)

    # 3. 현재 보유 종목 및 매매 히스토리
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("📋 Recent Trade History")
        st.dataframe(df.sort_values('timestamp', ascending=False).head(10), use_container_width=True)
        
    with col_right:
        st.subheader("🔥 Profit/Loss Heatmap")
        fig_heat = px.treemap(df, path=['code'], values='profit', color='profit',
                             color_continuous_scale='RdYlGn', title='종목별 수익 기여도')
        st.plotly_chart(fig_heat, use_container_width=True)

    # 4. AI 투자 복기 섹션
    st.divider()
    st.subheader("🤖 Gemini AI Investment Insights")
    if st.button("AI 매매 복기 생성"):
        from analytics.ai_journal import AITradingJournal
        # config에서 API 키 로드 로직 필요 (여기선 예시)
        api_key = st.secrets.get("GEMINI_API_KEY", "") 
        journal = AITradingJournal(api_key)
        
        with st.spinner("AI가 오늘의 매매를 분석 중입니다..."):
            # 실제 구현 시 macro_status 데이터 전달 필요
            review = journal.generate_review(df, "Nasdaq: +1.2%, USD/KRW: -0.5%")
            st.info(review)
else:
    st.warning("아직 거래 내역이 없습니다. 시스템이 거래를 시작하면 대시보드가 활성화됩니다.")

# 자동 새로고침 설정 (Streamlit 1.27.0+ 기준)
# st.rerun() # 실제 사용 시에는 QTimer나 st_autorefresh 등을 활용 권장
