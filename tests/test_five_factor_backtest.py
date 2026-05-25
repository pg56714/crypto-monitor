"""Five-factor backtest execution-timing tests."""

import unittest

from src.backtest.data import SymbolData
from src.backtest.five_factor import run_five_factor_backtest

_STEP_MS = 3_600_000


class FiveFactorBacktestTests(unittest.TestCase):
    """Tests for bar-close signal and next-bar entry behavior."""

    def test_session_filter_uses_entry_time(self) -> None:
        """Allow a trade when the next-bar entry time is inside the session."""
        data = _five_factor_signal_data(candle_count=5)

        trades = run_five_factor_backtest(
            data,
            start_ms=_STEP_MS,
            end_ms=3 * _STEP_MS,
            dedup_hours=0,
            session_start_hour=2,
            session_end_hour=3,
        )

        self.assertEqual([trade.entry_time_ms for trade in trades], [2 * _STEP_MS])

    def test_does_not_stack_entries_while_trade_is_open(self) -> None:
        """Keep one active simulated position per symbol."""
        data = _five_factor_signal_data(candle_count=6)

        trades = run_five_factor_backtest(
            data,
            start_ms=_STEP_MS,
            end_ms=4 * _STEP_MS,
            dedup_hours=0,
        )

        self.assertEqual(len(trades), 1)


def _five_factor_signal_data(*, candle_count: int) -> SymbolData:
    klines = []
    for i in range(candle_count):
        ts = i * _STEP_MS
        price = 100.0 + (i * 0.4)
        klines.append(
            [
                ts,
                price,
                price * 1.001,
                price * 0.999,
                price,
                0.0,
                0.0,
                100.0,
                0.0,
                0.0,
                100.0,
            ]
        )
    return SymbolData(
        symbol="TESTUSDT",
        signal_timeframe="1h",
        signal_step_ms=_STEP_MS,
        klines_signal=klines,
        funding_hist=[
            {"fundingTime": 0, "fundingRate": 0.0001},
            {"fundingTime": _STEP_MS - 1, "fundingRate": -0.0001},
        ],
        lsr_account=[{"timestamp": 0, "longShortRatio": 0.8}],
        lsr_position=[{"timestamp": 0, "longShortRatio": 2.1}],
    )


if __name__ == "__main__":
    unittest.main()
