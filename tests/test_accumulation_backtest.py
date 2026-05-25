"""Accumulation backtest execution-timing tests."""

import unittest

from src.backtest.accumulation import _find_limit_entry_fill
from src.scoring.entry_engine import EntryPlan


class AccumulationBacktestTests(unittest.TestCase):
    """Tests for limit-entry fill handling."""

    def test_intrabar_limit_fill_skips_same_candle_take_profit(self) -> None:
        """Do not use a high that may have happened before a mid-candle fill."""
        fill = _find_limit_entry_fill(
            [0, 1],
            [
                [0, 105.0, 120.0, 99.0, 110.0],
                [1, 100.0, 101.0, 98.0, 100.0],
            ],
            0,
            _entry_plan(),
        )

        self.assertIsNotNone(fill)
        assert fill is not None
        self.assertEqual(fill.entry_index, 0)
        self.assertEqual(fill.exit_start_index, 1)
        self.assertEqual(fill.entry_price, 100.0)

    def test_intrabar_limit_fill_keeps_same_candle_stop_check(self) -> None:
        """A low below stop after crossing the entry price should remain testable."""
        fill = _find_limit_entry_fill(
            [0, 1],
            [
                [0, 105.0, 120.0, 94.0, 100.0],
                [1, 100.0, 101.0, 98.0, 100.0],
            ],
            0,
            _entry_plan(),
        )

        self.assertIsNotNone(fill)
        assert fill is not None
        self.assertEqual(fill.entry_index, 0)
        self.assertEqual(fill.exit_start_index, 0)

    def test_open_below_stop_is_recorded_as_breached_fill(self) -> None:
        """A gap through the entry and stop should not make the trade disappear."""
        fill = _find_limit_entry_fill(
            [0],
            [[0, 94.0, 96.0, 93.0, 94.0]],
            0,
            _entry_plan(),
        )

        self.assertIsNotNone(fill)
        assert fill is not None
        self.assertEqual(fill.entry_price, 94.0)
        self.assertTrue(fill.stop_already_breached)


def _entry_plan() -> EntryPlan:
    return EntryPlan(
        entry_low=90.0,
        entry_high=100.0,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit_1=110.0,
        take_profit_2=120.0,
        risk_reward=2.0,
        is_valid=True,
    )


if __name__ == "__main__":
    unittest.main()
