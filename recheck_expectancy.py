#!/usr/bin/env python3
"""소액 실거래 재점검 — 파라미터 조정(2026-08-12) 이후 손익비/기대값 검증.

트레일링/손절 파라미터를 조정한 뒤, '새 파라미터로 체결된 거래만' 골라
손익비(평균익/평균손)와 건당 기대값이 양(+)으로 돌아섰는지 확인한다.

사용법:
    python recheck_expectancy.py                 # 2026-08-12 이후 실거래 집계
    python recheck_expectancy.py --since 2026-08-13
    python recheck_expectancy.py --db data/trading_history_real.db --since 2026-08-13

합격 기준(둘 다 충족):
    - 손익비 ≥ 0.90  (본전선. 승률 53% 기준 필요 손익비는 0.89)
    - 건당 기대값 > 0원
    - (표본) 청산 20건 이상이어야 통계적으로 의미 있음
"""
import argparse
import sqlite3
import sys

# 조정 이전(옛 파라미터) 기준선 — 첨부 로그 분석값
OLD_BASELINE = {"win_rate": 0.53, "avg_win": 382, "avg_loss": -558, "pl_ratio": 0.68, "exp": -63}

PASS_PL_RATIO = 0.90      # 본전 손익비
MIN_SAMPLE = 20           # 통계적 유의성 최소 표본


def analyze(db_path: str, since: str):
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT profit FROM trades WHERE type='SELL' AND timestamp >= ? ORDER BY timestamp",
        (since,),
    ).fetchall()
    conn.close()

    profits = [r[0] for r in rows if r[0] is not None]
    n = len(profits)
    if n == 0:
        print(f"⚠️  {since} 이후 청산(SELL) 거래가 없습니다. (DB: {db_path})")
        print("    봇을 재시작해 새 파라미터로 거래가 쌓인 뒤 다시 실행하세요.")
        return None

    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    win_rate = len(wins) / n
    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (sum(losses) / len(losses)) if losses else 0.0
    pl_ratio = (abs(avg_win) / abs(avg_loss)) if losses and avg_loss != 0 else float("inf")
    exp = sum(profits) / n
    # 본전 손익비 = (1-승률)/승률
    breakeven_pl = (1 - win_rate) / win_rate if win_rate > 0 else float("inf")

    print(f"📊 재점검 결과 ({since} 이후, DB: {db_path})")
    print(f"   청산 건수 : {n}건 (승 {len(wins)} / 패 {len(losses)})")
    print(f"   승률      : {win_rate*100:.1f}%   (본전 필요 손익비 {breakeven_pl:.2f})")
    print(f"   평균 익절 : {avg_win:+,.0f}원")
    print(f"   평균 손절 : {avg_loss:+,.0f}원")
    print(f"   손익비    : {pl_ratio:.2f}   [옛 파라미터 0.68]")
    print(f"   기대값    : {exp:+,.0f}원/건   [옛 파라미터 -63원]")
    print(f"   누적 손익 : {sum(profits):+,.0f}원")
    print()

    ok_ratio = pl_ratio >= PASS_PL_RATIO
    ok_exp = exp > 0
    ok_sample = n >= MIN_SAMPLE
    verdict = ok_ratio and ok_exp and ok_sample

    print(f"   [{'✅' if ok_ratio else '❌'}] 손익비 ≥ {PASS_PL_RATIO}")
    print(f"   [{'✅' if ok_exp else '❌'}] 기대값 > 0")
    print(f"   [{'✅' if ok_sample else '⏳'}] 표본 ≥ {MIN_SAMPLE}건 ({n}건)")
    print()
    if not ok_sample:
        print("⏳ 표본 부족 — 더 거래가 쌓인 뒤 재실행하세요.")
    elif verdict:
        print("✅ 합격 — 손익비가 양(+) 기대값 구간으로 전환되었습니다. 현 파라미터 유지 권장.")
    else:
        print("❌ 미달 — 파라미터 재조정 필요. (손절 추가 축소 또는 트레일링 재튜닝 검토)")
    return verdict


def main():
    ap = argparse.ArgumentParser(description="파라미터 조정 이후 손익비/기대값 재점검")
    ap.add_argument("--db", default="data/trading_history_real.db", help="SQLite DB 경로")
    ap.add_argument("--since", default="2026-08-12", help="집계 시작일 (봇 재시작일, YYYY-MM-DD)")
    args = ap.parse_args()
    result = analyze(args.db, args.since)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
