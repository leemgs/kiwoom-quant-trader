import time
import logging

import requests

try:
    import yfinance as yf  # 폴백용 (직접 조회 실패 시)
except Exception:  # noqa: BLE001
    yf = None


class MarketRegimeFilter:
    """시장 전체의 추세(강세장/하락장)를 판정하여 자동매매 진입을 게이트하는 필터.

    개별 종목의 모멘텀 신호와 별개로, 코스피/코스닥 등 '시장 대표 지수' 자체가
    하락 추세(bear market)에 있을 때는 신규 매수를 시도하지 않도록 하기 위한 장치다.
    (이미 보유 중인 포지션의 익절/손절/청산은 이 필터와 무관하게 항상 동작해야 하므로,
     이 필터는 오직 '신규 진입'만 차단한다.)

    하락장 판정 기준(지수별):
      1) 구조적 하락 추세 : 지수의 현재가가 이동평균선(기본 20일) 아래에 위치
      2) 급락 : 당일 등락률이 -crash_threshold(기본 -1.5%) 이하로 급락

    두 조건 중 하나라도 충족하면 해당 지수를 '하락'으로 본다.
    여러 지수를 감시할 때는 aggregation 설정으로 종합한다.
      - 'any' (기본): 감시 지수 중 하나라도 하락이면 시장 전체를 하락장으로 판정 (보수적/안전)
      - 'all'        : 감시 지수가 모두 하락일 때만 하락장으로 판정

    yfinance 호출 부하 및 rate limit을 고려하여 판정 결과를 cache_ttl초 동안 캐시한다.
    데이터 조회에 실패하면(네트워크 오류 등) 직전 정상 판정값을 재사용하며, 그마저 없으면
    매매를 불필요하게 전면 중단하지 않도록 '하락장 아님'(fail-open)으로 간주하고 경고만 남긴다.
    """

    # 지수 심볼 → 사람이 읽기 쉬운 이름 (로그용)
    _INDEX_NAMES = {
        "^KS11": "KOSPI",
        "^KQ11": "KOSDAQ",
        "^GSPC": "S&P500",
        "^IXIC": "NASDAQ",
    }

    def __init__(self, indices=None, ma_window=20, crash_threshold=0.015,
                 cache_ttl=300, aggregation="any"):
        # 감시 대상 지수 (기본: 코스피 + 코스닥) — 국내 종목 유니버스 기준 대표 지수
        self.indices = indices if indices else ["^KS11", "^KQ11"]
        # 추세 판정용 이동평균 기간(일)
        self.ma_window = int(ma_window)
        # 급락 판정 임계값 (0.015 = 당일 -1.5% 이하 급락 시 하락)
        self.crash_threshold = float(crash_threshold)
        # 판정 결과 캐시 유효시간(초)
        self.cache_ttl = int(cache_ttl)
        # 다중 지수 종합 방식 ('any' | 'all')
        self.aggregation = aggregation if aggregation in ("any", "all") else "any"

        # 캐시: {'bear': bool, 'reason': str, 'time': float}
        self._cache = {"bear": False, "reason": "", "time": 0.0}
        # 마지막으로 성공적으로 판정한 결과 (조회 실패 시 재사용)
        self._last_good = None

    def _index_name(self, symbol):
        return self._INDEX_NAMES.get(symbol, symbol)

    def _fetch_closes(self, symbol):
        """일봉 종가 리스트를 반환. 야후 차트 API(requests) 우선, 실패 시 yfinance 폴백.

        서버에 고정된 구버전 yfinance(0.2.31)가 야후 API 변경으로 조회에 계속 실패해
        하락장 필터가 무력화되던 문제를 피하기 위해, 대시보드와 동일한 경량 차트
        엔드포인트를 직접 호출한다.
        """
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
            url = f"https://{host}/v8/finance/chart/{symbol}?range=1y&interval=1d"
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                result = (data.get("chart", {}).get("result") or [None])[0]
                if not result:
                    continue
                quote = (result.get("indicators", {}).get("quote") or [{}])[0]
                closes = [c for c in (quote.get("close") or []) if c is not None]
                if len(closes) >= 2:
                    return [float(c) for c in closes]
            except Exception:  # noqa: BLE001
                continue
        # 폴백: yfinance
        if yf is not None:
            try:
                lookback_days = max(self.ma_window * 2, 40)
                hist = yf.Ticker(symbol).history(period=f"{lookback_days}d")
                closes = hist["Close"].dropna() if hist is not None and "Close" in hist else None
                if closes is not None and len(closes) >= 2:
                    return [float(c) for c in closes.tolist()]
            except Exception:  # noqa: BLE001
                pass
        return None

    def _evaluate_index(self, symbol):
        """단일 지수의 하락 여부를 판정. (is_bear, reason) 반환. 데이터 부재 시 (None, 사유)."""
        closes = self._fetch_closes(symbol)
        if not closes or len(closes) < 2:
            return None, f"{self._index_name(symbol)} 데이터 부족"

        current = float(closes[-1])
        prev_close = float(closes[-2])
        change_pct = (current - prev_close) / prev_close if prev_close else 0.0

        # 이동평균은 확보된 데이터가 부족하면 가능한 범위(최소 5)로 축소하여 계산
        window = min(self.ma_window, len(closes))
        window = max(window, 5) if len(closes) >= 5 else len(closes)
        ma = float(sum(closes[-window:]) / window)

        below_ma = current < ma
        acute_crash = change_pct <= -self.crash_threshold

        name = self._index_name(symbol)
        if below_ma or acute_crash:
            parts = []
            if below_ma:
                parts.append(f"{window}일 이평선({ma:,.1f}) 하회(현재 {current:,.1f})")
            if acute_crash:
                parts.append(f"당일 급락 {change_pct*100:+.2f}%")
            return True, f"{name}: " + ", ".join(parts)
        return False, f"{name}: 정상(현재 {current:,.1f} ≥ {window}일 이평선 {ma:,.1f}, 당일 {change_pct*100:+.2f}%)"

    def _compute(self):
        """감시 지수 전체를 평가하여 하락장 여부와 사유를 산출."""
        results = []   # (is_bear, reason) — 데이터 확보에 성공한 지수만
        for symbol in self.indices:
            try:
                is_bear, reason = self._evaluate_index(symbol)
            except Exception as e:
                logging.warning(f"⚠️ [MarketRegime] {self._index_name(symbol)} 지수 조회 에러: {e}")
                continue
            if is_bear is None:
                logging.warning(f"⚠️ [MarketRegime] {reason}")
                continue
            results.append((is_bear, reason))

        if not results:
            # 모든 지수 조회 실패 → 직전 정상값 재사용, 없으면 fail-open
            if self._last_good is not None:
                logging.warning("⚠️ [MarketRegime] 지수 데이터 조회 실패. 직전 판정값을 재사용합니다.")
                return self._last_good["bear"], self._last_good["reason"]
            logging.warning("⚠️ [MarketRegime] 지수 데이터 조회 실패 및 이전 판정값 없음. 하락장 아님으로 간주합니다.")
            return False, "지수 데이터 부재 (fail-open)"

        bears = [r for is_bear, r in results if is_bear]
        if self.aggregation == "all":
            bear = len(bears) == len(results)
        else:  # 'any'
            bear = len(bears) > 0

        if bear:
            reason = "; ".join(bears)
        else:
            reason = "; ".join(r for _, r in results)

        self._last_good = {"bear": bear, "reason": reason}
        return bear, reason

    def evaluate(self, force=False):
        """(is_bear_market, reason)을 반환. cache_ttl초 동안 결과를 캐시한다."""
        now = time.time()
        if not force and now - self._cache["time"] < self.cache_ttl and self._cache["time"] > 0:
            return self._cache["bear"], self._cache["reason"]

        bear, reason = self._compute()
        self._cache = {"bear": bear, "reason": reason, "time": now}
        return bear, reason

    def is_bear_market(self, force=False):
        """시장이 하락장이면 True."""
        bear, _ = self.evaluate(force=force)
        return bear
