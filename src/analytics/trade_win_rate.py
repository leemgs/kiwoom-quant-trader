"""Utilities for calculating trade outcome and win-rate dashboard data."""

import pandas as pd


OUTCOME_ORDER = ["수익", "손실", "보합"]


def build_win_rate_data(trades: pd.DataFrame):
    """Return outcome totals and a chronological cumulative win-rate series.

    Rows without a numeric profit are ignored.  A win rate is calculated from
    decided trades only (profit or loss), so zero-profit rows do not dilute it.
    """
    empty_outcomes = pd.DataFrame({"결과": OUTCOME_ORDER, "거래 수": [0, 0, 0]})
    empty_timeline = pd.DataFrame(columns=["timestamp", "누적 승률", "거래 번호"])
    if trades.empty or "profit" not in trades.columns:
        return empty_outcomes, empty_timeline

    analyzed = trades.copy()
    analyzed["profit"] = pd.to_numeric(analyzed["profit"], errors="coerce")
    analyzed = analyzed.dropna(subset=["profit"])
    if analyzed.empty:
        return empty_outcomes, empty_timeline

    analyzed["결과"] = analyzed["profit"].map(
        lambda value: "수익" if value > 0 else "손실" if value < 0 else "보합"
    )
    outcome_counts = analyzed["결과"].value_counts()
    outcomes = pd.DataFrame(
        {"결과": OUTCOME_ORDER, "거래 수": [int(outcome_counts.get(item, 0)) for item in OUTCOME_ORDER]}
    )

    decided = analyzed[analyzed["profit"] != 0].copy()
    if decided.empty:
        return outcomes, empty_timeline

    if "timestamp" in decided.columns:
        decided["timestamp"] = pd.to_datetime(decided["timestamp"], errors="coerce")
        decided = decided.sort_values("timestamp", kind="stable")
    else:
        decided["timestamp"] = pd.NaT

    decided["거래 번호"] = range(1, len(decided) + 1)
    decided["누적 승률"] = decided["profit"].gt(0).expanding().mean().mul(100)
    return outcomes, decided[["timestamp", "누적 승률", "거래 번호"]]
