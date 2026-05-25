"""Trade simulation tests."""

import unittest

from src.backtest.trade import Trade, simulate_trade


class TradeSimulationTests(unittest.TestCase):
    """Tests for linear futures trade P&L calculations."""

    def test_short_stop_uses_linear_return(self) -> None:
        """Calculate short stop loss from entry not exit price."""
        trade = Trade(
            symbol="TESTUSDT",
            strategy="five_factor",
            direction="short",
            entry_time_ms=0,
            entry_price=100.0,
            stop_loss=110.0,
            take_profit_1=80.0,
            take_profit_2=70.0,
        )

        simulate_trade(trade, [[1, 100.0, 110.0, 99.0, 105.0]], max_candles=1)

        self.assertEqual(trade.exit_reason, "stop")
        self.assertAlmostEqual(trade.pnl_pct or 0.0, -0.101)

    def test_short_take_profit_uses_linear_return(self) -> None:
        """Calculate short partial exits from entry price."""
        trade = Trade(
            symbol="TESTUSDT",
            strategy="five_factor",
            direction="short",
            entry_time_ms=0,
            entry_price=100.0,
            stop_loss=110.0,
            take_profit_1=80.0,
            take_profit_2=70.0,
        )

        simulate_trade(trade, [[1, 100.0, 101.0, 70.0, 75.0]], max_candles=1)

        self.assertEqual(trade.exit_reason, "tp2")
        self.assertAlmostEqual(trade.pnl_pct or 0.0, 0.249)


if __name__ == "__main__":
    unittest.main()
