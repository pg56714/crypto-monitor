"""Backtest report tests."""

import unittest

from src.backtest.report import _trades_to_returns
from src.backtest.trade import Trade

_DAY_MS = 86_400_000


class ReportReturnTests(unittest.TestCase):
    """Tests for report return-series date coverage."""

    def test_returns_cover_requested_backtest_window(self) -> None:
        """Include zero-return days before the first completed trade."""
        trade = Trade(
            symbol="TESTUSDT",
            strategy="accumulation",
            direction="long",
            entry_time_ms=2 * _DAY_MS,
            entry_price=100.0,
            stop_loss=90.0,
            take_profit_1=120.0,
            take_profit_2=130.0,
            exit_time_ms=3 * _DAY_MS,
            pnl_pct=0.1,
        )

        returns = _trades_to_returns([trade], start_ms=0, end_ms=5 * _DAY_MS)

        self.assertEqual(len(returns), 6)
        self.assertEqual(float(returns.iloc[0]), 0.0)
        self.assertAlmostEqual(float(returns.iloc[3]), 0.1)


if __name__ == "__main__":
    unittest.main()
