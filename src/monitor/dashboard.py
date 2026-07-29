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
st.set_page_config(page_title="Real-time Dashboard for Stock Quant Trader", layout="wide")

# 사이드바 상단 여백 최소화 스타일
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
            "<div style='font-size:11.5px;color:#e57373;margin-top:10px;'>"
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

st.sidebar.markdown(
    f"""
<div style='background-color:#ffffff;padding:15px;border-radius:10px;text-align:center;margin-bottom:15px;border:1px solid #e0e0e0;box-shadow:0 4px 6px rgba(0,0,0,0.05);'>
<h3 style='color:#03256C;margin:0 0 3px 0;font-weight:900;letter-spacing:1px;'>한국투자증권</h3>
<p style='color:#666;font-size:11px;margin:0 0 10px 0;font-weight:600;'>KOREA INVESTMENT &amp; SECURITIES</p>
<a href='https://apiportal.koreainvestment.com/' target='_blank' style='text-decoration:none;'>
<div style='background-color:#03256C;color:white;padding:6px 10px;border-radius:6px;font-size:12px;font-weight:bold;'>
🚀 KIS Developers (Open API)
</div>
</a>
</div>

<div style="margin-bottom:10px;">
<h4 style="margin:0 0 8px 0;font-size:16px;">💎 Trading Bot Control</h4>
<div style="background-color:{status_bg};padding:8px;border-radius:5px;color:{status_color};font-size:13px;font-weight:bold;margin-bottom:10px;line-height:1.5;">
시스템 상태: 🟢 가동 중<br>
자동매매 상태: {'⚔️ 전투 중' if is_any_trading else '💤 휴식 중'} (한국:{'O' if not is_kor_holiday else 'X'}, 미국:{'O' if not is_us_holiday else 'X'})
</div>
<p style="margin:0 0 5px 0;font-size:13px;"><strong>KIS Account:</strong> <code>{kis_account_no}-{kis_account_suffix}</code></p>
<p style="margin:0 0 5px 0;font-size:13px;"><strong>투자 운영 종류:</strong> <code style="color:{trading_type_color};font-weight:bold;">{trading_type_str}</code></p>
<p style="margin:0 0 5px 0;font-size:13px;"><strong>투자 운영 금액 (원금):</strong> <code>{investment_budget:,}원</code></p>
<p style="margin:0 0 5px 0;font-size:13px;"><strong>투자 운영 결과 (실제 총자산):</strong> <code style="color:{'#e53935' if real_total_assets < investment_budget else '#2e7d32' if real_total_assets > investment_budget else '#333'};font-weight:bold;">{real_total_assets:,}원</code></p>
<p style="margin:0 0 5px 0;font-size:13px;"><strong>증권 계좌 예수금 (현금):</strong> <code style="font-weight:bold;">{account_balance_str}</code></p>
<p style="margin:0 0 15px 0;font-size:13px;"><strong>{system_profit_label}:</strong> <code style="color:{'#e53935' if system_profit < 0 else '#2e7d32' if system_profit > 0 else '#333'};font-weight:bold;">{system_profit:+,}원</code></p>
</div>
""",
    unsafe_allow_html=True
)

# 실전 모드 손익 초기화
if not is_virtual:
    if 'show_reset_confirm' not in st.session_state:
        st.session_state['show_reset_confirm'] = False

    if not st.session_state['show_reset_confirm']:
        if st.sidebar.button("실전 손익 초기화 🔄", help="실전 거래 기록(DB)을 비워 누적 실현손익을 0원으로 리셋합니다."):
            st.session_state['show_reset_confirm'] = True
            st.rerun()
    else:
        st.sidebar.warning("기존 실현 손익액이 0원으로 완전히 초기화됩니다. 정말 수행하시겠습니까?")
        col1, col2 = st.sidebar.columns(2)
        with col1:
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
                st.sidebar.success("초기화 완료!")
                st.rerun()
        with col2:
            if st.button("아니오", use_container_width=True):
                st.session_state['show_reset_confirm'] = False
                st.rerun()

# 거래시간 expander
expander_title = f"⏰ {now.strftime('%Y-%m-%d %H:%M')} (한국:{'휴일' if is_kor_holiday else '평일'}, 미국:{'휴일' if is_us_holiday else '평일'}) ℹ️"
with st.sidebar.expander(expander_title):
    st.markdown("""
<table style="width:100%;border-collapse:collapse;font-size:11.5px;margin-top:5px;border:1px solid #e0e0e0;border-radius:6px;">
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
      <td style="text-align:center;padding:6px;color:#333;">월 ~ 금<br><span style="font-size:9.5px;color:#888;">(공휴일 제외)</span></td>
      <td style="text-align:center;padding:6px;color:#333;">월 ~ 금<br><span style="font-size:9.5px;color:#888;">(공휴일 제외)</span></td>
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
      <td style="text-align:center;padding:6px;color:#e53935;font-weight:bold;">15:15<br><span style="font-size:9.5px;font-weight:normal;color:#e53935;">(미수 방지)</span></td>
      <td style="text-align:center;padding:6px;color:#777;">-</td>
    </tr>
  </tbody>
</table>
""", unsafe_allow_html=True)

refresh_rate = st.sidebar.slider("새로고침 간격(초)", 5, 60, 30)

st.sidebar.markdown("---")
st.sidebar.markdown(
    """
    <a href="https://leemgs.github.io/stock-quant-trader-kis/" target="_blank" style="text-decoration:none;">
        <div style='background-color:#f8f9fa;color:#333;padding:10px;border-radius:6px;text-align:center;border:1px solid #ddd;font-weight:bold;font-size:14px;'>
            🏠 프로젝트 공식 홈페이지
        </div>
    </a>
    """,
    unsafe_allow_html=True
)

# ── 메인 콘텐츠 ───────────────────────────────────────────────────────────────
st.markdown("<h2 style='font-size:28px;font-weight:bold;margin-bottom:20px;'>🚀 Real-time Dashboard for Stock Quant Trader</h2>", unsafe_allow_html=True)

# 시장 국면 (지수 200일선 기준) — 현재 시장이 상승장인지 하락장인지 한눈에 표시
_regime_col1, _regime_col2 = st.columns([5, 1])
with _regime_col2:
    _force_regime = st.button("🔄 시장 국면 새로고침", use_container_width=True,
                              help="지수 데이터를 강제로 다시 조회합니다.")
_regimes = get_market_regime(force=_force_regime)
st.markdown(render_market_regime_table(_regimes), unsafe_allow_html=True)

INITIAL_SEED = investment_budget
INVESTMENT_PERIOD_MONTH = int(os.getenv('INVESTMENT_PERIOD_MONTH', '1'))
INVESTMENT_INCOME_GOAL = float(os.getenv('INVESTMENT_INCOME_GOAL', '100000'))
TARGET_GOAL = INVESTMENT_INCOME_GOAL

col1, col2, col3, col4 = st.columns(4)

if not is_virtual:
    display_profit = system_profit
    display_current_total = real_total_assets
else:
    display_profit = df['profit'].sum() if not df.empty else 0.0
    display_current_total = INITIAL_SEED + display_profit

if not df.empty:
    total_trades = len(df)
    win_rate = (df['profit'] > 0).mean() * 100
    buy_count = len(df[df['type'].str.upper() == 'BUY']) if 'type' in df.columns else 0
    sell_count = len(df[df['type'].str.upper() == 'SELL']) if 'type' in df.columns else 0
else:
    total_trades = 0
    win_rate = 0.0
    buy_count = 0
    sell_count = 0

unfilled_buy = 0
unfilled_sell = 0

with col1:
    st.metric("총 거래 횟수", f"{total_trades}회")
    st.markdown(f"""
        <div style="font-size:11px;color:#888;margin-top:-10px;line-height:1.3;">
            체결수량 (매수: {buy_count}회 , 매도: {sell_count}회)<br>
            미체결수량 (매수: {unfilled_buy}회 , 매도: {unfilled_sell}회)
        </div>
    """, unsafe_allow_html=True)
col2.metric("승률", f"{win_rate:.1f}%")
col3.metric("누적 손익", f"{display_profit:,.0f}원", delta=f"{display_profit:,.0f}")
col4.metric("목표 달성률", f"{(display_profit/TARGET_GOAL)*100:.1f}%")

st.divider()
st.subheader(f"🎯 {INVESTMENT_PERIOD_MONTH}개월 수익 도전 ({INITIAL_SEED:,}원 → {TARGET_GOAL:,}원)")
progress = min(1.0, max(0.0, display_current_total / TARGET_GOAL))
st.progress(progress)
st.write(f"현재 총 자산: **{display_current_total:,.0f}원** / 목표 자산: **{TARGET_GOAL:,.0f}원**")

if not df.empty:
    st.subheader("📈 Cumulative Equity Curve")
    df_chart = df[['timestamp', 'profit']].copy()
    df_chart['timestamp'] = pd.to_datetime(df_chart['timestamp'])
    df_chart = df_chart.sort_values('timestamp')
    df_chart['cum_profit'] = df_chart['profit'].cumsum()
    df_chart['timestamp'] = df_chart['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')

    fig_curve = px.line(df_chart, x='timestamp', y='cum_profit', title='누적 수익률 추이')
    st.plotly_chart(fig_curve, use_container_width=True)
    del fig_curve  # 즉시 해제하여 메모리 절약

    col_left, col_right = st.columns(2)

    with col_left:
        col_trade_title, col_trade_btn = st.columns([3, 1.2])
        with col_trade_title:
            st.subheader("📋 Recent Trade History")
        with col_trade_btn:
            csv_data = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="CSV 다운로드 💾",
                data=csv_data,
                file_name=f"trade_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        st.dataframe(df.sort_values('timestamp', ascending=False).head(10), use_container_width=True)

    with col_right:
        st.subheader("🔥 Profit/Loss Heatmap")
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

    st.divider()
    st.subheader("🤖 Gemini AI Investment Insights")
    if st.button("AI 매매 복기 생성"):
        from analytics.ai_journal import AITradingJournal
        api_key = os.getenv("GEMINI_API_KEY", "")
        journal = AITradingJournal(api_key)
        with st.spinner("AI가 오늘의 매매를 분석 중입니다..."):
            review = journal.generate_review(df, "Nasdaq: +1.2%, USD/KRW: -0.5%")
            st.info(review)
else:
    st.warning("아직 거래 내역이 없습니다. 시스템이 거래를 시작하면 차트와 상세 내역이 활성화됩니다.")

# ── 시스템 로그 ───────────────────────────────────────────────────────────────
st.divider()

col_log_title, col_log_btn = st.columns([4, 1])
with col_log_title:
    st.subheader("🤖 System Activity Logs (실시간 시스템 로그)")

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
    height:350px;
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
# time.sleep() + st.rerun() 패턴은 매 실행마다 메모리를 쌓는 원인.
# streamlit-autorefresh 없이도 meta refresh 방식으로 메모리 누수 없이 새로고침.
gc.collect()

st.markdown(
    f"""
    <meta http-equiv="refresh" content="{refresh_rate}">
    """,
    unsafe_allow_html=True
)
