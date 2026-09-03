import sys
import os
import gc
import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timezone, timedelta
import holidays
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv(override=True)

# sys.path 설정: src 폴더를 포함하여 analytics 등을 임포트 가능하도록 함
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# ── 페이지 설정 ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="QuantFlow · AI Stock Command Center",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 앱 전체 디자인 시스템. Streamlit의 동작은 유지하면서 카드, 내비게이션, 차트
# 컨테이너를 하나의 현대적인 인포그래픽 언어로 통일한다.
st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+KR:wght@400;500;600;700;800&display=swap');
        :root {
            --navy: #081426; --panel: #ffffff; --canvas: #f3f7fb;
            --blue: #2563eb; --cyan: #06b6d4; --mint: #10b981;
            --ink: #10213a; --muted: #64748b; --line: #e2e8f0;
        }
        html, body, [class*="css"] { font-family: 'Inter', 'Noto Sans KR', sans-serif; }
        .stApp { background: radial-gradient(circle at 82% 0%, #e0f2fe 0, transparent 27%), var(--canvas); color: var(--ink); }
        .block-container { max-width: 1480px; padding-top: 1.6rem; padding-bottom: 3rem; }
        header[data-testid="stHeader"] { background: transparent; }
        [data-testid="stSidebarUserContent"] {
            padding-top: 1.25rem !important;
            padding-left: 1rem; padding-right: 1rem;
        }
        section[data-testid="stSidebar"] { background: var(--navy); border-right: 1px solid rgba(255,255,255,.08); }
        section[data-testid="stSidebar"] * { color: #dbeafe; }
        section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] hr { border-color: rgba(255,255,255,.1); }
        section[data-testid="stSidebar"] div[role="radiogroup"] { gap: .35rem; }
        section[data-testid="stSidebar"] label[data-baseweb="radio"] {
            padding: .7rem .75rem; border-radius: 12px; transition: .18s ease;
            border: 1px solid transparent;
        }
        section[data-testid="stSidebar"] label[data-baseweb="radio"]:hover {
            background: rgba(59,130,246,.13); border-color: rgba(96,165,250,.22); transform: translateX(2px);
        }
        section[data-testid="stSidebar"] label[data-baseweb="radio"]:has(input:checked) {
            background: linear-gradient(135deg, rgba(37,99,235,.9), rgba(6,182,212,.72));
            box-shadow: 0 8px 22px rgba(2,132,199,.22);
        }
        section[data-testid="stSidebar"] [data-testid="stSlider"] { padding: .25rem .2rem; }
        .brand-block { padding: .4rem .35rem 1rem; }
        .brand-mark { display:flex; align-items:center; gap:.7rem; font-size:1.2rem; font-weight:800; color:#fff; }
        .brand-icon { width:38px;height:38px;display:grid;place-items:center;border-radius:12px;background:linear-gradient(135deg,#3b82f6,#06b6d4);box-shadow:0 8px 22px rgba(6,182,212,.28); }
        .brand-caption { color:#7dd3fc !important; font-size:.69rem; font-weight:600; letter-spacing:.13em; margin:.45rem 0 0 3.1rem; }
        .hero-panel { position:relative; overflow:hidden; padding:1.55rem 1.7rem; border-radius:22px; color:#fff; background:linear-gradient(120deg,#081426 0%,#102d55 58%,#075985 100%); box-shadow:0 18px 45px rgba(15,23,42,.15); margin-bottom:1rem; }
        .hero-panel:after { content:"";position:absolute;width:260px;height:260px;right:-70px;top:-120px;border:48px solid rgba(34,211,238,.12);border-radius:50%; }
        .hero-eyebrow { color:#67e8f9;font-size:.72rem;letter-spacing:.14em;font-weight:800;margin-bottom:.45rem; }
        .hero-title { font-size:clamp(1.35rem,2.4vw,2rem);font-weight:800;line-height:1.25;margin:0;letter-spacing:-.035em; }
        .hero-copy { color:#bfdbfe;font-size:.86rem;margin:.55rem 0 0;max-width:720px; }
        .hero-meta { position:absolute;right:1.6rem;bottom:1.5rem;display:flex;align-items:center;gap:.45rem;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.14);border-radius:999px;padding:.45rem .75rem;font-size:.72rem;backdrop-filter:blur(8px); }
        .live-dot { width:7px;height:7px;border-radius:50%;background:#34d399;box-shadow:0 0 0 5px rgba(52,211,153,.13); }
        .kpi-grid { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.8rem;margin:0 0 1.25rem; }
        .kpi-card { background:rgba(255,255,255,.92);border:1px solid rgba(226,232,240,.95);border-radius:16px;padding:1rem 1.05rem;box-shadow:0 6px 22px rgba(15,23,42,.045); }
        .kpi-label { color:var(--muted);font-size:.7rem;font-weight:700;letter-spacing:.035em;text-transform:uppercase; }
        .kpi-value { color:var(--ink);font-size:1.35rem;font-weight:800;line-height:1.35;margin-top:.22rem; }
        .kpi-note { color:#94a3b8;font-size:.67rem;margin-top:.2rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }
        .section-heading { display:flex;align-items:center;gap:.85rem;margin:.25rem 0 1rem; }
        .section-icon { display:grid;place-items:center;width:42px;height:42px;border-radius:13px;background:#dbeafe;font-size:1.15rem; }
        .section-title { margin:0;font-size:1.05rem;font-weight:800;color:var(--ink); }
        .section-copy { margin:.15rem 0 0;color:var(--muted);font-size:.76rem; }
        div[data-testid="stPlotlyChart"], div[data-testid="stDataFrame"], div[data-testid="stExpander"] { background:#fff;border:1px solid var(--line);border-radius:16px;padding:.45rem;box-shadow:0 5px 20px rgba(15,23,42,.04);overflow:hidden; }
        div[data-testid="stMetric"] { background:#fff;border:1px solid var(--line);border-radius:15px;padding:.85rem 1rem;box-shadow:0 4px 16px rgba(15,23,42,.04); }
        .stButton > button, .stDownloadButton > button { border-radius:11px;border:1px solid #cbd5e1;font-weight:700;min-height:2.55rem; }
        .stButton > button:hover, .stDownloadButton > button:hover { border-color:var(--blue);color:var(--blue);box-shadow:0 6px 18px rgba(37,99,235,.12); }
        div[data-testid="stAlert"] { border-radius:14px; }
        @media (max-width: 800px) {
            .block-container { padding-top:1rem;padding-left:1rem;padding-right:1rem; }
            .kpi-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
            .hero-meta { position:static;width:max-content;margin-top:1rem; }
        }
        @media (max-width: 480px) { .kpi-grid { grid-template-columns:1fr; } }
    </style>
    """,
    unsafe_allow_html=True
)

# ── 네비게이션 메뉴 정의 및 쿼리 파라미터 헬퍼 ──────────────────────────────
# 대시보드 내용을 한 화면에 모두 나열하지 않고, 사이드바 메뉴로 섹션을 선택해
# 스크롤 없이 열람할 수 있도록 한다. 선택 상태는 URL 쿼리 파라미터(view)에
# 저장하여, 30초 자동 새로고침(meta refresh)에도 선택한 메뉴가 유지되도록 한다.
MENU_ITEMS = [
    "🌐 시장 국면",
    "🎯 수익 도전 현황",
    "📈 Cumulative Equity Curve",
    "📋 Recent Trade History",
    "🔥 Profit/Loss Heatmap",
    "🤖 Gemini AI Investment Insights",
    "🖥️ System Activity Logs",
]

# 거래 시간 안내 표 (사이드바 대신 '수익 도전 현황' 섹션의 expander에서 사용)
MARKET_HOURS_TABLE_HTML = """
<table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:5px;border:1px solid #e0e0e0;border-radius:6px;">
  <thead>
    <tr style="border-bottom:2px solid #e0e0e0;background-color:#f8f9fa;">
      <th style="text-align:left;padding:6px;font-weight:bold;color:#333;">구분</th>
      <th style="text-align:center;padding:6px;font-weight:bold;color:#03256C;">한국</th>
      <th style="text-align:center;padding:6px;font-weight:bold;color:#a53535;">미국</th>
    </tr>
  </thead>
  <tbody>
    <tr style="border-bottom:1px solid #eee;">
      <td style="padding:6px;font-weight:bold;color:#555;background-color:#fafafa;">운영 요일</td>
      <td style="text-align:center;padding:6px;color:#333;">월 ~ 금<br><span style="font-size:11px;color:#888;">(공휴일 제외)</span></td>
      <td style="text-align:center;padding:6px;color:#333;">월 ~ 금<br><span style="font-size:11px;color:#888;">(공휴일 제외)</span></td>
    </tr>
    <tr style="border-bottom:1px solid #eee;">
      <td style="padding:6px;font-weight:bold;color:#555;background-color:#fafafa;">개장 준비</td>
      <td style="text-align:center;padding:6px;color:#333;">08:50 ~ 09:00</td>
      <td style="text-align:center;padding:6px;color:#333;">22:30 ~ 23:30</td>
    </tr>
    <tr style="border-bottom:1px solid #eee;">
      <td style="padding:6px;font-weight:bold;color:#555;background-color:#fafafa;">자동 매매</td>
      <td style="text-align:center;padding:6px;color:#2e7d32;font-weight:bold;">09:00 ~ 15:15</td>
      <td style="text-align:center;padding:6px;color:#c62828;font-weight:bold;">23:30 ~ 05:00</td>
    </tr>
    <tr>
      <td style="padding:6px;font-weight:bold;color:#555;background-color:#fafafa;">강제 청산</td>
      <td style="text-align:center;padding:6px;color:#e53935;font-weight:bold;">15:15<br><span style="font-size:11px;font-weight:normal;color:#e53935;">(미수 방지)</span></td>
      <td style="text-align:center;padding:6px;color:#777;">-</td>
    </tr>
  </tbody>
</table>
"""

def _get_query_param(key, default=None):
    """Streamlit 버전에 무관하게 쿼리 파라미터 값을 읽는다."""
    try:  # Streamlit >= 1.30
        val = st.query_params.get(key)
        if val is not None:
            return val
    except Exception:
        pass
    try:  # Streamlit < 1.30
        vals = st.experimental_get_query_params().get(key)
        if vals:
            return vals[0]
    except Exception:
        pass
    return default

def _set_query_param(key, value):
    """Streamlit 버전에 무관하게 쿼리 파라미터 값을 설정한다."""
    try:  # Streamlit >= 1.30
        st.query_params[key] = value
        return
    except Exception:
        pass
    try:  # Streamlit < 1.30
        st.experimental_set_query_params(**{key: value})
    except Exception:
        pass

# ── 환경변수 ────────────────────────────────────────────────────────────────────
kis_account_no = os.getenv('KIS_ACCOUNT_NO', 'Unknown')
kis_account_suffix = os.getenv('KIS_ACCOUNT_SUFFIX', '01')
investment_budget = int(os.getenv('INVESTMENT_BUDGET', '10000'))
is_virtual = os.getenv('KIS_VIRTUAL_TRADING', 'true').lower() == 'true'
db_path = "data/trading_history_mock.db" if is_virtual else "data/trading_history_real.db"

# ── 주식 종목명 매핑 ─────────────────────────────────────────────────────────────
STOCK_NAMES = {
    # 한국 주식 (UNIVERSE)
    "035720": "카카오",
    "004020": "현대제철",
    "015760": "한국전력",
    "006360": "GS건설",
    "323410": "카카오뱅크",
    "011200": "HMM",
    "032640": "LG유플러스",
    "003490": "대한항공",
    "207940": "삼성바이오로직스",
    "000660": "SK하이닉스",
    "373220": "LG에너지솔루션",
    "005380": "현대차",
    "293490": "카카오게임즈",
    "005930": "삼성전자",
    "034020": "두산에너빌리티",
    "018260": "삼성에스디에스",
    "006400": "삼성SDI",
    "006280": "GC녹십자",
    "039130": "하나투어",
    "080160": "모두투어",
    "000270": "기아",
    "093370": "후성",
    "204320": "HL만도",
    "0183J0": "TIGER미국우주테크(ETF)",
    "042660": "한화오션",
    "047040": "대우건설",
    "032820": "우리기술",
    "042700": "한미반도체",
    "010170": "대한광통신",
    "001440": "대한전선",
    "229200": "KODEX코스닥150(ETF)",
    "090710": "휴림로봇",
    "067310": "하나마이크론",
    
    # 미국 주식 (US_UNIVERSE)
    "AAPL.US": "Apple",
    "MSFT.US": "Microsoft",
    "GOOGL.US": "Google",
    "TSLA.US": "Tesla",
    "NVDA.US": "NVIDIA",
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Google",
    "TSLA": "Tesla",
    "NVDA": "NVIDIA"
}

@st.cache_data(ttl=3600)
def get_stock_name(code: str) -> str:
    if not code:
        return ""
    code_str = str(code).strip()
    if code_str in STOCK_NAMES:
        return STOCK_NAMES[code_str]
    
    # API 동적 조회 시도 (한국 주식인 경우)
    if code_str.isdigit() and len(code_str) == 6:
        try:
            broker = get_broker(
                os.getenv('KIS_APP_KEY', ''),
                os.getenv('KIS_APP_SECRET', ''),
                os.getenv('KIS_ACCOUNT_NO', ''),
                os.getenv('KIS_ACCOUNT_SUFFIX', '01'),
                os.getenv('KIS_VIRTUAL_TRADING', 'true').lower() == 'true'
            )
            if broker:
                res = broker.api.fetch_price(code_str)
                if isinstance(res, dict) and 'output' in res:
                    name = res['output'].get('hts_kor_isnm')
                    if name:
                        return name
        except Exception:
            pass
            
    return code_str

# ── 시장 국면 (지수 200일선 기준) ────────────────────────────────────────────
# 주요 글로벌 지수를 200일 이동평균선과 비교하여 상승장/하락장을 판정한다.
# (현재가 ≥ 200일선 → 상승장 / 현재가 < 200일선 → 하락장)
MARKET_REGIME_INDICES = [
    {"flag": "🇺🇸", "name": "미국 S&P500", "symbol": "^GSPC"},
    {"flag": "🇰🇷", "name": "한국 KOSPI", "symbol": "^KS11"},
    {"flag": "🇭🇰", "name": "홍콩 HSI", "symbol": "^HSI"},
    {"flag": "🇯🇵", "name": "일본 Nikkei225", "symbol": "^N225"},
]

# 지수별 마지막 정상 조회값 캐시 (성공만 저장). 프로세스 수명 동안 유지.
#   symbol -> {"price", "ma", "diff_pct", "is_bull", "time"}
# 실패 결과는 캐시하지 않으므로, 일시적 오류는 다음 새로고침에서 곧바로 재시도된다.
_MARKET_REGIME_CACHE = {}
_MARKET_REGIME_GOOD_TTL = 3600  # 정상값 유효시간(초): 200일선은 하루 단위로 변하므로 1시간이면 충분

def _fetch_index_closes(symbol: str):
    """야후 파이낸스 차트 API를 requests로 직접 호출하여 일봉 종가 리스트를 반환.

    오래된 yfinance(예: 0.2.31)의 크럼/복호화 실패 이슈를 피하기 위해 경량 차트
    엔드포인트를 브라우저 User-Agent로 직접 조회한다. query1/query2 두 호스트를
    순차 시도한다. 실패 시 예외를 발생시킨다.
    """
    import requests
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    last_err = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v8/finance/chart/{symbol}?range=1y&interval=1d"
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            result = (data.get("chart", {}).get("result") or [None])[0]
            if not result:
                raise ValueError("빈 응답(result 없음)")
            quote = (result.get("indicators", {}).get("quote") or [{}])[0]
            closes = [c for c in (quote.get("close") or []) if c is not None]
            if len(closes) >= 2:
                return closes
            raise ValueError(f"종가 데이터 부족(len={len(closes)})")
        except Exception as e:
            last_err = e
            continue
    raise last_err if last_err else RuntimeError("알 수 없는 조회 오류")

def _fetch_index_yfinance(symbol: str):
    """폴백: yfinance로 종가 리스트 조회."""
    import yfinance as yf
    hist = yf.Ticker(symbol).history(period="1y")
    closes = hist["Close"].dropna() if hist is not None and "Close" in hist else None
    if closes is not None and len(closes) >= 2:
        return [float(c) for c in closes.tolist()]
    raise ValueError("yfinance 종가 데이터 부족")

def get_market_regime(ma_window: int = 200, force: bool = False):
    """주요 글로벌 지수의 200일선 대비 등락률로 상승장/하락장을 판정한다.

    반환: [{flag, name, symbol, price, ma, diff_pct, is_bull, ok, stale, error}, ...]
    - 성공값은 _MARKET_REGIME_GOOD_TTL초 동안 캐시(정상값만 저장).
    - 조회 실패 시 직전 정상값이 있으면 재사용(stale=True)하고, 없으면 ok=False.
    - force=True면 캐시를 무시하고 강제 재조회.
    """
    import time as _time
    results = []
    now = _time.time()
    for item in MARKET_REGIME_INDICES:
        symbol = item["symbol"]
        row = {**item, "price": None, "ma": None, "diff_pct": None,
               "is_bull": None, "ok": False, "stale": False, "error": None}

        cached = _MARKET_REGIME_CACHE.get(symbol)
        # 신선한 정상 캐시가 있으면 그대로 사용
        if not force and cached and now - cached["time"] < _MARKET_REGIME_GOOD_TTL:
            row.update({k: cached[k] for k in ("price", "ma", "diff_pct", "is_bull")})
            row["ok"] = True
            results.append(row)
            continue

        try:
            try:
                closes = _fetch_index_closes(symbol)
            except Exception:
                # 직접 호출 실패 시 yfinance로 폴백
                closes = _fetch_index_yfinance(symbol)
            price = float(closes[-1])
            window = min(ma_window, len(closes))
            ma = float(sum(closes[-window:]) / window)
            diff_pct = ((price - ma) / ma * 100) if ma else 0.0
            payload = {"price": price, "ma": ma, "diff_pct": diff_pct, "is_bull": price >= ma}
            _MARKET_REGIME_CACHE[symbol] = {**payload, "time": now}
            row.update(payload)
            row["ok"] = True
        except Exception as e:
            err = str(e)[:120]
            print(f"Market regime fetch error ({symbol}): {e}")
            if cached:  # 직전 정상값 재사용(다소 오래되었을 수 있음)
                row.update({k: cached[k] for k in ("price", "ma", "diff_pct", "is_bull")})
                row["ok"] = True
                row["stale"] = True
            else:
                row["error"] = err
        results.append(row)
    return results

def render_market_regime_table(regimes):
    """시장 국면 표를 HTML로 렌더링."""
    rows_html = ""
    for r in regimes:
        if r["ok"]:
            if r["is_bull"]:
                state_html = "<span style='color:#2e7d32;font-weight:bold;'>🟢 상승장</span>"
                diff_color = "#2e7d32"
                sign = "+" if r["diff_pct"] >= 0 else "−"
            else:
                state_html = "<span style='color:#e53935;font-weight:bold;'>🔴 하락장</span>"
                diff_color = "#e53935"
                sign = "+" if r["diff_pct"] >= 0 else "−"
            price_str = f"{r['price']:,.2f}"
            diff_str = f"{sign}{abs(r['diff_pct']):.2f}%"
            diff_cell = f"<span style='color:{diff_color};font-weight:bold;'>{diff_str}</span>"
            if r.get("stale"):
                state_html += " <span style='font-size:10px;color:#f9a825;'>(이전값)</span>"
        else:
            err = r.get("error")
            tip = f" title='{err}'" if err else ""
            state_html = f"<span style='color:#888;'{tip}>⚪ 조회 실패</span>"
            price_str = "-"
            diff_cell = "<span style='color:#888;'>-</span>"
        rows_html += (
            "<tr style='border-bottom:1px solid #eee;'>"
            f"<td style='padding:8px 12px;font-weight:600;color:#333;'>{r['flag']} {r['name']}</td>"
            f"<td style='padding:8px 12px;text-align:center;'>{state_html}</td>"
            f"<td style='padding:8px 12px;text-align:right;color:#333;'>{price_str}</td>"
            f"<td style='padding:8px 12px;text-align:right;'>{diff_cell}</td>"
            "</tr>"
        )

    # 전부 실패한 경우 안내 문구
    all_failed = all((not r["ok"]) for r in regimes)
    footer = ""
    if all_failed:
        footer = (
            "<div style='font-size:12px;color:#e57373;margin-top:10px;'>"
            "⚠️ 지수 데이터를 가져오지 못했습니다. 서버의 인터넷 연결(야후 파이낸스 접근)을 확인하고 "
            "'🔄 시장 국면 새로고침' 버튼을 눌러 다시 시도해 주세요.</div>"
        )
    return f"""
<div style="background-color:#ffffff;border:1px solid #e0e0e0;border-radius:10px;padding:16px 18px;margin-bottom:20px;box-shadow:0 4px 6px rgba(0,0,0,0.05);">
  <div style="font-size:17px;font-weight:bold;color:#03256C;margin-bottom:12px;">
    🌐 시장 국면 <span style="font-size:12px;color:#888;font-weight:normal;">(지수 200일선 기준)</span>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:14px;">
    <thead>
      <tr style="border-bottom:2px solid #e0e0e0;background-color:#f8f9fa;">
        <th style="text-align:left;padding:8px 12px;color:#555;">시장</th>
        <th style="text-align:center;padding:8px 12px;color:#555;">상태</th>
        <th style="text-align:right;padding:8px 12px;color:#555;">지수</th>
        <th style="text-align:right;padding:8px 12px;color:#555;">200일선 대비</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
  {footer}
</div>
"""

# ── 데이터 로드 (캐시 TTL=10초) ─────────────────────────────────────────────────
@st.cache_data(ttl=10)
def get_data(_db_path: str):
    """DB에서 거래 내역을 조회한다. 캐시 적용으로 매 rerun 시 DB 연결을 방지."""
    try:
        conn = sqlite3.connect(_db_path)
        # 최근 500건만 로드하여 메모리 절약
        df = pd.read_sql(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT 500",
            conn
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()

@st.cache_resource
def get_broker(app_key, app_secret, account_no, account_suffix, is_virtual):
    """KISBroker 인스턴스를 프로세스 수명 동안 한 번만 생성한다. 설정이 변경되면 새로 생성한다."""
    try:
        from broker.kis_api import KISBroker
        config = {
            'auth': {
                "kis_app_key": app_key,
                "kis_app_secret": app_secret,
                "kis_account_no": account_no,
                "kis_account_suffix": account_suffix,
                "kis_virtual_trading": is_virtual,
            }
        }
        if not app_key or not app_secret:
            return None
        return KISBroker(config)
    except Exception as e:
        print(f"KISBroker init error: {e}")
        return None

# ── 계좌 잔고 조회 (캐시 TTL=30초) ────────────────────────────────────────────
@st.cache_data(ttl=10)
def get_account_balance():
    """우선 로컬 파일 캐시(data/balance_cache.json)를 읽고, 없거나 오래된 경우 KIS API 직접 조회를 수행한다."""
    import json
    cache_file = "data/balance_cache.json"
    
    # 1. 로컬 캐시 파일 조회 시도
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            updated_at = datetime.strptime(data.get("updated_at"), "%Y-%m-%d %H:%M:%S")
            if (datetime.now() - updated_at).total_seconds() < 120:
                return {'cash': data['cash'], 'total_assets': data['total_assets']}
        except Exception:
            pass

    # 2. 캐시가 없거나 오래되었으면 KIS API 직접 호출
    try:
        broker = get_broker(
            os.getenv('KIS_APP_KEY', ''),
            os.getenv('KIS_APP_SECRET', ''),
            os.getenv('KIS_ACCOUNT_NO', ''),
            os.getenv('KIS_ACCOUNT_SUFFIX', '01'),
            os.getenv('KIS_VIRTUAL_TRADING', 'true').lower() == 'true'
        )
        if broker is None:
            return "설정 필요"
        res = broker.api.fetch_balance()
        if isinstance(res, dict) and res.get('rt_cd') == '0':
            output2 = res.get('output2', [])
            if output2:
                cash = int(output2[0].get('dnca_tot_amt', 0))
                total_assets = int(output2[0].get('tot_evlu_amt', cash))
                
                # 다음 조회를 위해 파일에도 저장
                try:
                    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump({
                            "cash": cash,
                            "total_assets": total_assets,
                            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }, f, ensure_ascii=False, indent=4)
                except Exception:
                    pass
                    
                return {'cash': cash, 'total_assets': total_assets}
            else:
                return "오류 (응답 데이터가 비어 있습니다)"
        else:
            msg = res.get('msg1', '조회 실패') if isinstance(res, dict) else '응답 오류'
            return f"오류 ({msg})"
    except Exception as e:
        print(f"Error fetching account balance: {e}")
        return f"에러 ({str(e)})"

# ── 로그 파일 tail (전체 읽기 방지) ────────────────────────────────────────────
def get_recent_logs(log_path="logs/trading.log", num_lines=30):
    """파일 끝에서부터 역방향으로 읽어 전체 파일 메모리 로드를 방지한다."""
    if not os.path.exists(log_path):
        return ["로그 파일이 존재하지 않습니다."]
    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)  # 파일 끝으로 이동
            file_size = f.tell()
            block_size = 8192
            lines = []
            remainder = b""
            pos = file_size
            while pos > 0 and len(lines) < num_lines:
                read_size = min(block_size, pos)
                pos -= read_size
                f.seek(pos)
                chunk = f.read(read_size) + remainder
                chunk_lines = chunk.split(b"\n")
                remainder = chunk_lines[0]
                lines = chunk_lines[1:] + lines
            if remainder:
                lines = [remainder] + lines
            result = []
            for line in lines:
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded:
                    result.append(decoded)
            return result[-num_lines:]
    except Exception as e:
        return [f"로그를 읽는 중 오류가 발생했습니다: {str(e)}"]

def format_logs_to_html(logs):
    formatted_lines = []
    for line in reversed(logs):
        escaped_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if " - INFO - " in escaped_line:
            if any(emoji in escaped_line for emoji in ["🔥", "🚀", "🎯", "✅", "⚡", "💎"]):
                color = "#4fc3f7"
            else:
                color = "#e0e0e0"
        elif " - WARNING - " in escaped_line or "⚠️" in escaped_line:
            color = "#ffb74d"
        elif " - ERROR - " in escaped_line or "❌" in escaped_line or "🚨" in escaped_line:
            color = "#e57373"
        else:
            color = "#f5f5f5"
        formatted_lines.append(
            f'<div style="color:{color};margin-bottom:4px;border-bottom:1px solid #2d2d2d;'
            f'padding-bottom:4px;font-family:monospace;font-size:13px;">{escaped_line}</div>'
        )
    return "".join(formatted_lines)

# ── 시장 상태 계산 ────────────────────────────────────────────────────────────
kst = timezone(timedelta(hours=9))
now = datetime.now(kst)
today = now.date()

kr_holidays = holidays.CountryHoliday('KR')
us_holidays_cal = holidays.CountryHoliday('US')
is_kor_holiday = today in kr_holidays
is_us_holiday = today in us_holidays_cal

is_kor_trading = not is_kor_holiday and now.weekday() < 5 and (
    (now.hour == 8 and now.minute >= 50) or
    (now.hour >= 9 and now.hour < 15) or
    (now.hour == 15 and now.minute <= 20)
)

us_tz = timezone(timedelta(hours=-4))
now_us = datetime.now(us_tz)
is_us_trading = (
    not is_us_holiday and
    now_us.weekday() < 5 and
    (now_us.hour > 9 or (now_us.hour == 9 and now_us.minute >= 30)) and
    (now_us.hour < 16 or (now_us.hour == 16 and now_us.minute == 0))
)
is_any_trading = is_kor_trading or is_us_trading

# ── 데이터 로드 ─────────────────────────────────────────────────────────────────
df = get_data(db_path)

# 종목명 컬럼(name) 추가 및 배치 (Recent Trade History 출력용)
if not df.empty and 'code' in df.columns:
    df['name'] = df['code'].apply(get_stock_name)
    cols = list(df.columns)
    if 'code' in cols and 'name' in cols:
        code_idx = cols.index('code')
        # code 바로 옆에 name 컬럼 배치
        cols.insert(code_idx + 1, cols.pop(cols.index('name')))
        df = df[cols]

total_profit = df['profit'].sum() if not df.empty else 0
current_total = investment_budget + total_profit

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

if is_virtual:
    system_profit = total_profit
    system_profit_label = "시스템 누적 실현손익 (모의)"
else:
    # 실전 실현손익은 총자산 변화량이 아니라 거래 기록(DB)의 손익 합계로 계산한다.
    # 총자산 변화량 방식은 계좌 입금·출금이 그대로 손익으로 오인되는 문제가 있다
    # (예: 4만원 입금 → 거래 0건인데 '실현손익 +40,000원'으로 표시).
    system_profit = total_profit
    system_profit_label = "시스템 누적 실현손익 (실전)"

# ── 사이드바 ──────────────────────────────────────────────────────────────────
status_bg = "#e8f5e9" if is_kor_trading else "#f5f5f5"
status_color = "#2e7d32" if is_kor_trading else "#555555"
trading_type_str = "모의" if is_virtual else "실전"
trading_type_color = "#2e7d32" if is_virtual else "#e53935"

# 계좌/상태 정보 패널 HTML — 사이드바를 간결하게 유지하기 위해 여기서는 렌더링하지
# 않고, '🎯 수익 도전 현황' 섹션에서 출력한다. (사이드바 스크롤 없이 메뉴 접근성 개선)
# 증권사 브랜딩/Open API 링크는 사이드바 하단의 심플 웹링크로 대체되었다.
# 폰트 스케일 통일: 제목 16px · 본문 14px · 보조 12px
account_panel_html = f"""
<div style="background:#fff;border:1px solid #e2e8f0;border-radius:18px;padding:1.15rem 1.25rem;margin-bottom:1rem;box-shadow:0 5px 20px rgba(15,23,42,.04);">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;"><b style="font-size:15px;color:#10213a;">Trading Bot Control</b><span style="font-size:11px;background:{status_bg};color:{status_color};padding:5px 9px;border-radius:999px;font-weight:800;">● SYSTEM ONLINE</span></div>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1px;background:#e2e8f0;border:1px solid #e2e8f0;border-radius:13px;overflow:hidden;">
  <div style="background:#f8fafc;padding:12px;"><small style="color:#64748b;">자동매매</small><br><b>{'⚔️ 거래 진행 중' if is_any_trading else '◷ 시장 대기 중'}</b></div>
  <div style="background:#f8fafc;padding:12px;"><small style="color:#64748b;">KIS 계좌</small><br><b>{kis_account_no}-{kis_account_suffix}</b> · <span style="color:{trading_type_color};">{trading_type_str}</span></div>
  <div style="background:#f8fafc;padding:12px;"><small style="color:#64748b;">운영 원금</small><br><b>{investment_budget:,}원</b></div>
  <div style="background:#f8fafc;padding:12px;"><small style="color:#64748b;">현재 총자산</small><br><b>{real_total_assets:,}원</b></div>
  <div style="background:#f8fafc;padding:12px;"><small style="color:#64748b;">사용 가능 현금</small><br><b>{account_balance_str}</b></div>
  <div style="background:#f8fafc;padding:12px;"><small style="color:#64748b;">누적 실현손익</small><br><b style="color:{'#ef4444' if system_profit < 0 else '#10b981' if system_profit > 0 else '#10213a'};">{system_profit:+,}원</b></div>
</div>
</div>
"""

# ── 네비게이션 메뉴 (섹션 선택) — 사이드바 최상단 배치 ────────────────────────
# URL 쿼리 파라미터에 저장된 선택값으로 초기화하여 자동 새로고침에도 유지한다.
_default_idx = 0
_qp_view = _get_query_param("view")
if _qp_view is not None:
    try:
        _i = int(_qp_view)
        if 0 <= _i < len(MENU_ITEMS):
            _default_idx = _i
    except (ValueError, TypeError):
        pass
if "nav_view" not in st.session_state:
    st.session_state["nav_view"] = MENU_ITEMS[_default_idx]

# 좌측 브랜드 및 Home 링크 — 배포 호스트에 관계없이 현재 앱의 루트로 이동한다.
st.sidebar.markdown(
    """
    <div class="brand-block">
      <div class="brand-mark"><span class="brand-icon">↗</span><span>QuantFlow</span></div>
      <div class="brand-caption">AI TRADING SYSTEM</div>
    </div>
    <a href="/" target="_self" style="text-decoration:none;">
      <div style="background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);padding:9px 11px;border-radius:11px;font-weight:700;font-size:13px;margin-bottom:14px;">⌂ &nbsp;대시보드 홈</div>
    </a>
    """,
    unsafe_allow_html=True
)

st.sidebar.markdown("<p style='font-size:11px;font-weight:800;letter-spacing:.12em;color:#64748b;margin:0 0 6px 8px;'>WORKSPACE</p>", unsafe_allow_html=True)
selected_menu = st.sidebar.radio(
    "메뉴 선택", MENU_ITEMS, key="nav_view", label_visibility="collapsed"
)
# 현재 선택을 쿼리 파라미터에 반영 (다음 자동 새로고침 시 복원용)
_set_query_param("view", str(MENU_ITEMS.index(selected_menu)))
st.sidebar.markdown("<hr><p style='font-size:11px;font-weight:800;letter-spacing:.12em;color:#64748b;margin:0 0 6px 8px;'>LIVE CONTROL</p>", unsafe_allow_html=True)

# 새로고침 간격 슬라이더 (사이드바에 상시 배치). 값은 쿼리 파라미터(refresh)로
# 영속화하여 자동 새로고침의 전체 리로드 후에도 유지되도록 한다.
# 범위: 5초 ~ 600초(10분)
try:
    _cur_rate = int(_get_query_param("refresh", "30"))
except (ValueError, TypeError):
    _cur_rate = 30
_cur_rate = min(600, max(5, _cur_rate))
refresh_rate = st.sidebar.slider("새로고침 간격(초)", 5, 600, _cur_rate, step=5)
if refresh_rate != _cur_rate:
    _set_query_param("refresh", str(refresh_rate))
st.sidebar.caption(f"현재: {refresh_rate}초 ({refresh_rate/60:.1f}분) · 범위 5초~10분")

# 프로젝트 공식 홈페이지 + 한국투자증권 Open API 링크 (심플 웹링크)
st.sidebar.markdown(
    """
    <a href="https://leemgs.github.io/stock-quant-trader-kis/" target="_blank" style="text-decoration:none;">
        <div style='background-color:#f8f9fa;color:#333;padding:10px;border-radius:6px;text-align:center;border:1px solid #ddd;font-weight:bold;font-size:14px;margin-top:8px;'>
            🏠 프로젝트 공식 홈페이지
        </div>
    </a>
    <a href="https://apiportal.koreainvestment.com/" target="_blank" style="text-decoration:none;">
        <div style='background-color:#03256C;color:#ffffff;padding:10px;border-radius:6px;text-align:center;border:1px solid #03256C;font-weight:bold;font-size:14px;margin-top:8px;'>
            🏦 한국투자증권 Open API
        </div>
    </a>
    """,
    unsafe_allow_html=True
)

# ── 공통 계산 (요약 KPI 및 각 섹션 공용) ──────────────────────────────────────
INITIAL_SEED = investment_budget
INVESTMENT_PERIOD_MONTH = int(os.getenv('INVESTMENT_PERIOD_MONTH', '1'))
INVESTMENT_INCOME_GOAL = float(os.getenv('INVESTMENT_INCOME_GOAL', '100000'))
TARGET_GOAL = INVESTMENT_INCOME_GOAL

if not is_virtual:
    display_profit = system_profit
    display_current_total = real_total_assets
else:
    display_profit = df['profit'].sum() if not df.empty else 0.0
    display_current_total = INITIAL_SEED + display_profit

if not df.empty:
    total_trades = len(df)
    decided_profits = pd.to_numeric(df['profit'], errors='coerce').dropna()
    decided_profits = decided_profits[decided_profits != 0]
    win_rate = (decided_profits > 0).mean() * 100 if not decided_profits.empty else 0.0
    buy_count = len(df[df['type'].str.upper() == 'BUY']) if 'type' in df.columns else 0
    sell_count = len(df[df['type'].str.upper() == 'SELL']) if 'type' in df.columns else 0
else:
    total_trades = 0
    win_rate = 0.0
    buy_count = 0
    sell_count = 0

unfilled_buy = 0
unfilled_sell = 0

# ── 메인 콘텐츠 ───────────────────────────────────────────────────────────────
# 선택 메뉴별 인포그래픽 설명. 사용자가 데이터의 의미를 즉시 이해하도록 한다.
MENU_DESCRIPTIONS = {
    MENU_ITEMS[0]: ("GLOBAL SIGNAL MAP", "글로벌 시장 국면", "주요 지수와 200일 이동평균선으로 시장의 위험 온도를 한눈에 확인합니다."),
    MENU_ITEMS[1]: ("GOAL TRACKER", "수익 도전 현황", "운영 자산, 실현 손익, 목표까지의 여정을 실시간으로 추적합니다."),
    MENU_ITEMS[2]: ("PERFORMANCE", "누적 자산 곡선", "거래가 쌓일수록 변화하는 전략의 누적 성과를 시각화합니다."),
    MENU_ITEMS[3]: ("TRADE INTELLIGENCE", "최근 거래 기록", "체결 내역과 승률 흐름을 함께 살펴보고 전략의 품질을 진단합니다."),
    MENU_ITEMS[4]: ("ALLOCATION MAP", "손익 히트맵", "종목별 수익 기여도와 손실 집중 구간을 면적으로 비교합니다."),
    MENU_ITEMS[5]: ("AI COPILOT", "Gemini 투자 인사이트", "최근 매매 데이터를 AI로 복기해 다음 의사결정에 활용합니다."),
    MENU_ITEMS[6]: ("SYSTEM OBSERVABILITY", "시스템 활동 로그", "자동매매 엔진의 상태와 이벤트를 실시간으로 모니터링합니다."),
}

# 헤더와 KPI를 반응형 인포그래픽 카드로 구성한다.
_profit_color = '#e53935' if display_profit < 0 else '#2e7d32' if display_profit > 0 else '#333'
_goal_rate = (display_profit / TARGET_GOAL * 100) if TARGET_GOAL else 0.0
_goal_color = '#e53935' if _goal_rate < 0 else '#2e7d32' if _goal_rate > 0 else '#333'

st.markdown(
    f"""
<div class="hero-panel">
  <div class="hero-eyebrow">QUANTITATIVE INVESTMENT COMMAND CENTER</div>
  <h1 class="hero-title">데이터가 이끄는 더 선명한 투자</h1>
  <p class="hero-copy">시장 신호부터 거래 성과, AI 인사이트까지 하나의 실시간 워크스페이스에서 확인하세요.</p>
  <div class="hero-meta"><span class="live-dot"></span> LIVE · {now.strftime('%Y.%m.%d %H:%M')} KST</div>
</div>
<div class="kpi-grid">
  <div class="kpi-card"><div class="kpi-label">▦ Total Trades</div><div class="kpi-value">{total_trades:,}<small style="font-size:.7rem;color:#64748b"> 건</small></div><div class="kpi-note">매수 {buy_count} · 매도 {sell_count} · 미체결 {unfilled_buy + unfilled_sell}</div></div>
  <div class="kpi-card"><div class="kpi-label">◎ Win Rate</div><div class="kpi-value">{win_rate:.1f}<small style="font-size:.7rem;color:#64748b">%</small></div><div class="kpi-note">확정 손익 거래 기준</div></div>
  <div class="kpi-card"><div class="kpi-label">↗ Realized P/L</div><div class="kpi-value" style="color:{_profit_color};">{display_profit:+,.0f}<small style="font-size:.7rem"> 원</small></div><div class="kpi-note">누적 실현 손익</div></div>
  <div class="kpi-card"><div class="kpi-label">◈ Goal Progress</div><div class="kpi-value" style="color:{_goal_color};">{_goal_rate:.1f}<small style="font-size:.7rem">%</small></div><div class="kpi-note">목표 {TARGET_GOAL:,.0f}원 기준</div></div>
</div>
<div class="section-heading"><div class="section-icon">{selected_menu.split()[0]}</div><div><h2 class="section-title">{MENU_DESCRIPTIONS[selected_menu][1]}</h2><p class="section-copy">{MENU_DESCRIPTIONS[selected_menu][2]}</p></div></div>
""",
    unsafe_allow_html=True
)

# ── 선택된 메뉴에 해당하는 섹션만 렌더링 (스크롤 최소화) ──────────────────────
if selected_menu == "🌐 시장 국면":
    _regime_col1, _regime_col2 = st.columns([5, 1])
    with _regime_col2:
        _force_regime = st.button("🔄 시장 국면 새로고침", use_container_width=True,
                                  help="지수 데이터를 강제로 다시 조회합니다.")
    _regimes = get_market_regime(force=_force_regime)
    st.markdown(render_market_regime_table(_regimes), unsafe_allow_html=True)

elif selected_menu == "🎯 수익 도전 현황":
    # 계좌/봇 상태 정보 패널 (사이드바에서 이전됨)
    st.markdown(account_panel_html, unsafe_allow_html=True)
    # 통일된 폰트 스케일(제목 16px · 본문 14px)로 렌더링 — Streamlit 기본 제목/본문 크기 편차 제거
    st.markdown(
        f"<h4 style='margin:0 0 8px 0;font-size:16px;'>🎯 {INVESTMENT_PERIOD_MONTH}개월 수익 도전 "
        f"({INITIAL_SEED:,}원 → {TARGET_GOAL:,.0f}원)</h4>",
        unsafe_allow_html=True
    )
    progress = min(1.0, max(0.0, display_current_total / TARGET_GOAL))
    st.progress(progress)
    st.markdown(
        f"<p style='font-size:14px;margin:6px 0 0 0;'>현재 총 자산: <b>{display_current_total:,.0f}원</b> "
        f"/ 목표 자산: <b>{TARGET_GOAL:,.0f}원</b></p>",
        unsafe_allow_html=True
    )

    # ── 설정 및 정보 (사이드바에서 이전됨) ──────────────────────────────────
    st.divider()
    st.markdown("<h4 style='margin:0 0 8px 0;font-size:16px;'>⚙️ 설정 및 정보</h4>", unsafe_allow_html=True)

    # 실전 모드 손익 초기화
    if not is_virtual:
        if 'show_reset_confirm' not in st.session_state:
            st.session_state['show_reset_confirm'] = False
        if not st.session_state['show_reset_confirm']:
            if st.button("실전 손익 초기화 🔄", help="실전 거래 기록(DB)을 비워 누적 실현손익을 0원으로 리셋합니다."):
                st.session_state['show_reset_confirm'] = True
                st.rerun()
        else:
            st.warning("기존 실현 손익액이 0원으로 완전히 초기화됩니다. 정말 수행하시겠습니까?")
            _rc1, _rc2, _sp = st.columns([1, 1, 4])
            with _rc1:
                if st.button("예", use_container_width=True):
                    try:
                        from core.database import TradeDatabase
                        db = TradeDatabase("data/trading_history_real.db")
                        with sqlite3.connect(db.db_path) as conn:
                            conn.execute("DELETE FROM trades")
                            conn.commit()
                    except Exception as e:
                        print(f"Error clearing real trades DB: {e}")
                    get_data.clear()
                    st.session_state['show_reset_confirm'] = False
                    st.success("초기화 완료!")
                    st.rerun()
            with _rc2:
                if st.button("아니오", use_container_width=True):
                    st.session_state['show_reset_confirm'] = False
                    st.rerun()

    # 거래 시간 안내
    expander_title = f"⏰ {now.strftime('%Y-%m-%d %H:%M')} (한국:{'휴일' if is_kor_holiday else '평일'}, 미국:{'휴일' if is_us_holiday else '평일'}) ℹ️"
    with st.expander(expander_title):
        st.markdown(MARKET_HOURS_TABLE_HTML, unsafe_allow_html=True)

elif selected_menu == "📈 Cumulative Equity Curve":
    st.subheader("📈 Cumulative Equity Curve")
    if not df.empty:
        df_chart = df[['timestamp', 'profit']].copy()
        df_chart['timestamp'] = pd.to_datetime(df_chart['timestamp'])
        df_chart = df_chart.sort_values('timestamp')
        df_chart['cum_profit'] = df_chart['profit'].cumsum()
        df_chart['timestamp'] = df_chart['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
        fig_curve = px.line(df_chart, x='timestamp', y='cum_profit', title='누적 수익률 추이')
        st.plotly_chart(fig_curve, use_container_width=True)
        del fig_curve  # 즉시 해제하여 메모리 절약
    else:
        st.warning("아직 거래 내역이 없습니다. 시스템이 거래를 시작하면 차트가 활성화됩니다.")

elif selected_menu == "📋 Recent Trade History":
    col_trade_title, col_trade_btn = st.columns([3, 1.2])
    with col_trade_title:
        st.subheader("📋 Recent Trade History")
    if not df.empty:
        with col_trade_btn:
            csv_data = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="CSV 다운로드 💾",
                data=csv_data,
                file_name=f"trade_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        st.dataframe(df.sort_values('timestamp', ascending=False).head(20), use_container_width=True)

        # 출력 테이블과 동일한 거래 데이터를 기반으로 자동매매 성과를 요약한다.
        # 보합 거래는 별도로 표시하며 승률은 방향이 결정된 거래(수익/손실)만으로 계산한다.
        from analytics.trade_win_rate import build_win_rate_data

        outcome_df, win_rate_timeline = build_win_rate_data(df)
        wins = int(outcome_df.loc[outcome_df['결과'] == '수익', '거래 수'].iloc[0])
        losses = int(outcome_df.loc[outcome_df['결과'] == '손실', '거래 수'].iloc[0])
        breakeven = int(outcome_df.loc[outcome_df['결과'] == '보합', '거래 수'].iloc[0])
        decided_trades = wins + losses
        auto_win_rate = wins / decided_trades * 100 if decided_trades else 0.0

        st.divider()
        st.subheader("🎯 자동매매 승률 현황")
        st.caption("Recent Trade History 전체 조회 데이터 기준 · 승률 = 수익 거래 ÷ (수익 + 손실 거래)")
        metric_win_rate, metric_wins, metric_losses, metric_breakeven = st.columns(4)
        metric_win_rate.metric("자동매매 승률", f"{auto_win_rate:.1f}%")
        metric_wins.metric("수익 거래", f"{wins}건")
        metric_losses.metric("손실 거래", f"{losses}건")
        metric_breakeven.metric("보합 거래", f"{breakeven}건")

        chart_outcomes, chart_trend = st.columns([1, 2])
        with chart_outcomes:
            fig_outcomes = px.pie(
                outcome_df,
                names='결과',
                values='거래 수',
                hole=0.58,
                color='결과',
                color_discrete_map={'수익': '#2e7d32', '손실': '#e53935', '보합': '#9e9e9e'},
                title='거래 결과 구성',
            )
            fig_outcomes.update_traces(textinfo='label+value', hovertemplate='%{label}: %{value}건 (%{percent})<extra></extra>')
            fig_outcomes.update_layout(margin=dict(l=10, r=10, t=50, b=10), legend_title_text='결과')
            st.plotly_chart(fig_outcomes, use_container_width=True)

        with chart_trend:
            if not win_rate_timeline.empty:
                fig_win_rate = px.line(
                    win_rate_timeline,
                    x='거래 번호',
                    y='누적 승률',
                    markers=True,
                    title='거래 진행에 따른 누적 승률',
                    hover_data={'timestamp': True, '거래 번호': True, '누적 승률': ':.1f'},
                )
                fig_win_rate.add_hline(
                    y=50,
                    line_dash='dash',
                    line_color='#9e9e9e',
                    annotation_text='50% 기준선',
                )
                fig_win_rate.update_yaxes(range=[0, 100], ticksuffix='%')
                fig_win_rate.update_layout(margin=dict(l=10, r=10, t=50, b=10))
                st.plotly_chart(fig_win_rate, use_container_width=True)
            else:
                st.info("수익 또는 손실이 확정된 거래가 생기면 누적 승률 추이가 표시됩니다.")

        del fig_outcomes
        if 'fig_win_rate' in locals():
            del fig_win_rate
    else:
        st.warning("아직 거래 내역이 없습니다. 시스템이 거래를 시작하면 상세 내역이 활성화됩니다.")

elif selected_menu == "🔥 Profit/Loss Heatmap":
    st.subheader("🔥 Profit/Loss Heatmap")
    if not df.empty:
        df_group = df.groupby('code', as_index=False)['profit'].sum()
        df_group['abs_profit'] = df_group['profit'].abs().fillna(0)
        # To avoid ZeroDivisionError in plotly's weighted average when weights sum to zero for any group,
        # we ensure abs_profit is at least a small positive number.
        df_group.loc[df_group['abs_profit'] <= 0, 'abs_profit'] = 1e-5
        fig_heat = px.treemap(df_group, path=['code'], values='abs_profit', color='profit',
                              color_continuous_scale='RdYlGn', title='종목별 수익 기여도',
                              hover_data=['profit'])
        st.plotly_chart(fig_heat, use_container_width=True)
        del fig_heat  # 즉시 해제
    else:
        st.warning("아직 거래 내역이 없습니다. 시스템이 거래를 시작하면 히트맵이 활성화됩니다.")

elif selected_menu == "🤖 Gemini AI Investment Insights":
    st.subheader("🤖 Gemini AI Investment Insights")
    st.caption("Google Gemini로 최근 매매를 복기합니다. (`.env`의 GEMINI_API_KEY 필요)")
    st.caption("ℹ️ 이 화면에서는 생성 중 결과 유실을 막기 위해 자동 새로고침이 일시 중지됩니다.")

    col_gen, col_clear = st.columns([1, 1])
    with col_gen:
        gen_clicked = st.button("AI 매매 복기 생성", use_container_width=True)
    with col_clear:
        if st.button("결과 지우기", use_container_width=True):
            st.session_state.pop('ai_review', None)
            st.rerun()

    if gen_clicked:
        from analytics.ai_journal import AITradingJournal
        api_key = os.getenv("GEMINI_API_KEY", "")
        with st.spinner("AI가 오늘의 매매를 분석 중입니다... (모델에 따라 최대 1~2분 소요될 수 있습니다)"):
            journal = AITradingJournal(api_key)
            review = journal.generate_review(df, "Nasdaq: +1.2%, USD/KRW: -0.5%")
        # 결과를 세션에 저장하여 재실행(rerun)에도 유지 (생성에 오래 걸려도 소실 방지)
        st.session_state['ai_review'] = review

    # 저장된 결과가 있으면 표시 (버튼을 다시 누르지 않아도 유지됨)
    review = st.session_state.get('ai_review')
    if review:
        # 실패 원인이 특정되도록 메시지 접두어(❌/⚠️)에 따라 심각도 표시
        if review.startswith("❌"):
            st.error(review)
        elif review.startswith("⚠️"):
            st.warning(review)
        else:
            st.success(review)

elif selected_menu == "🖥️ System Activity Logs":
    col_log_title, col_log_btn = st.columns([4, 1])
    with col_log_title:
        st.subheader("🖥️ System Activity Logs (실시간 시스템 로그)")
    with col_log_btn:
        log_file_path = "logs/trading.log"
        if os.path.exists(log_file_path):
            try:
                with open(log_file_path, "r", encoding="utf-8") as f:
                    log_content = f.read()
                st.download_button(
                    label="로그 다운로드 💾",
                    data=log_content,
                    file_name=f"trading_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
            except Exception:
                pass

    log_lines = get_recent_logs()
    formatted_html = format_logs_to_html(log_lines)
    log_box_html = f"""
<div style="
    background-color:#1e1e1e;
    padding:15px;
    border-radius:8px;
    height:450px;
    overflow-y:auto;
    border:1px solid #333;
    box-shadow:inset 0 0 10px rgba(0,0,0,0.5);
">
    {formatted_html}
</div>
<p style="font-size:11px;color:#888;margin-top:5px;text-align:right;">※ 최신 로그가 상단에 표시됩니다. (새로고침 간격: {refresh_rate}초)</p>
"""
    st.markdown(log_box_html, unsafe_allow_html=True)

# ── 메모리 정리 후 자동 새로고침 ─────────────────────────────────────────────
gc.collect()

# ⚠️ 자동 새로고침은 iframe 내부 JS 타이머로 구현한다.
#
# 과거의 `<meta http-equiv="refresh">` 방식은 브라우저가 한 번 파싱하면 리로드를
# '예약'해 버려서, 다른 화면(예: 로그)에서 타이머가 걸린 뒤 사이드바로 Gemini AI
# 화면에 진입(soft rerun)하면 태그를 지워도 예약된 리로드가 취소되지 않아 복기 생성
# 도중 페이지가 리로드되는 문제가 있었다.
#
# components.html로 만든 iframe의 setTimeout은, 해당 컴포넌트가 다음 실행에서
# 렌더링되지 않으면(=Gemini 화면) iframe이 DOM에서 제거되며 타이머도 함께 취소된다.
# 따라서 Gemini AI 화면에서는 생성이 아무리 오래 걸려도 리로드되지 않는다.
if selected_menu != "🤖 Gemini AI Investment Insights":
    import streamlit.components.v1 as _components
    _components.html(
        f"""
        <script>
          // 부모(대시보드) 페이지를 refresh_rate초 후 새로고침
          setTimeout(function() {{
            window.parent.location.reload();
          }}, {int(refresh_rate) * 1000});
        </script>
        """,
        height=0,
    )
