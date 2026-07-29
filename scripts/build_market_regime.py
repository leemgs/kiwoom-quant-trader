#!/usr/bin/env python3
"""시장 국면(지수 200일선 기준) 데이터를 생성하여 docs/data/market_regime.json에 저장.

GitHub Actions 크론에서 주기적으로 실행되어, 정적 GitHub Pages 대시보드가 읽을
JSON을 갱신한다. 야후 파이낸스의 공개 차트 API만 사용하므로 인증/비밀키가 전혀
필요 없다. (계좌 정보 등 민감 데이터는 다루지 않는다.)

판정 기준:
  - 현재가 >= 200일 이동평균선  → 상승장(🟢)
  - 현재가 <  200일 이동평균선  → 하락장(🔴)

조회 실패 시 기존 JSON의 직전 정상값을 유지하여 대시보드가 비지 않도록 한다.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta

import requests

# 감시 대상 지수 (국내 종목 유니버스 기준 + 주요 글로벌 지수)
INDICES = [
    {"flag": "🇺🇸", "name": "미국 S&P500", "symbol": "^GSPC"},
    {"flag": "🇰🇷", "name": "한국 KOSPI", "symbol": "^KS11"},
    {"flag": "🇭🇰", "name": "홍콩 HSI", "symbol": "^HSI"},
    {"flag": "🇯🇵", "name": "일본 Nikkei225", "symbol": "^N225"},
]
MA_WINDOW = 200
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "data", "market_regime.json")


def fetch_closes(symbol: str):
    """야후 차트 API에서 1년치 일봉 종가 리스트를 반환. query1/query2 순차 시도."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    last_err = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v8/finance/chart/{symbol}?range=1y&interval=1d"
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            result = (data.get("chart", {}).get("result") or [None])[0]
            if not result:
                raise ValueError("빈 응답(result 없음)")
            quote = (result.get("indicators", {}).get("quote") or [{}])[0]
            closes = [c for c in (quote.get("close") or []) if c is not None]
            if len(closes) >= 2:
                return [float(c) for c in closes]
            raise ValueError(f"종가 데이터 부족(len={len(closes)})")
        except Exception as e:  # noqa: BLE001
            last_err = e
            continue
    raise last_err if last_err else RuntimeError("알 수 없는 조회 오류")


def load_previous():
    """기존 JSON을 로드하여 심볼별 직전 정상값 맵을 반환(조회 실패 시 폴백용)."""
    prev = {}
    try:
        with open(OUT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for row in data.get("indices", []):
            if row.get("ok"):
                prev[row["symbol"]] = row
    except Exception:  # noqa: BLE001
        pass
    return prev


def build():
    prev = load_previous()
    results = []
    for item in INDICES:
        symbol = item["symbol"]
        row = {**item, "price": None, "ma": None, "diff_pct": None,
               "is_bull": None, "ok": False, "stale": False}
        try:
            closes = fetch_closes(symbol)
            price = float(closes[-1])
            window = min(MA_WINDOW, len(closes))
            ma = sum(closes[-window:]) / window
            diff_pct = ((price - ma) / ma * 100) if ma else 0.0
            row.update({
                "price": round(price, 2),
                "ma": round(ma, 2),
                "diff_pct": round(diff_pct, 2),
                "is_bull": price >= ma,
                "ok": True,
            })
            print(f"[OK] {item['name']}: {price:,.2f} ({diff_pct:+.2f}% vs {window}d MA)")
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] {item['name']} ({symbol}): {e}", file=sys.stderr)
            if symbol in prev:  # 직전 정상값 유지
                row.update({k: prev[symbol].get(k) for k in ("price", "ma", "diff_pct", "is_bull")})
                row["ok"] = True
                row["stale"] = True
        results.append(row)

    kst = timezone(timedelta(hours=9))
    now = datetime.now(timezone.utc)
    payload = {
        "generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_at_kst": now.astimezone(kst).strftime("%Y-%m-%d %H:%M:%S KST"),
        "ma_window": MA_WINDOW,
        "source": "Yahoo Finance (v8 chart API)",
        "indices": results,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[WROTE] {os.path.abspath(OUT_PATH)}")
    return payload


if __name__ == "__main__":
    build()
