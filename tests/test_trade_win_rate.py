import unittest

import pandas as pd

from src.analytics.trade_win_rate import build_win_rate_data


class BuildWinRateDataTest(unittest.TestCase):
    def test_classifies_outcomes_and_excludes_breakeven_from_rate(self):
        trades = pd.DataFrame(
            {
                "timestamp": ["2026-01-03", "2026-01-01", "2026-01-02", "bad date"],
                "profit": [30, 10, -5, 0],
            }
        )

        outcomes, timeline = build_win_rate_data(trades)

        self.assertEqual(dict(zip(outcomes["결과"], outcomes["거래 수"])), {"수익": 2, "손실": 1, "보합": 1})
        self.assertEqual(timeline["거래 번호"].tolist(), [1, 2, 3])
        self.assertAlmostEqual(timeline["누적 승률"].iloc[-1], 2 / 3 * 100)

    def test_handles_missing_or_non_numeric_profit(self):
        outcomes, timeline = build_win_rate_data(pd.DataFrame({"profit": [None, "unknown"]}))

        self.assertEqual(outcomes["거래 수"].sum(), 0)
        self.assertTrue(timeline.empty)


if __name__ == "__main__":
    unittest.main()
