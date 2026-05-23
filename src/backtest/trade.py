"""Trade dataclass and candle-by-candle exit simulation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_FEE = 0.001  # 0.1% round trip (0.05% each side)


@dataclass
class Trade:
    """Single simulated trade with entry, exit, and P&L fields."""

    symbol: str
    strategy: str
    direction: str
    entry_time_ms: int
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    exit_time_ms: int | None = None
    exit_reason: str | None = None
    pnl_pct: float | None = None


def simulate_trade(
    trade: Trade,
    future_klines: list[list[Any]],
    *,
    max_candles: int,
) -> Trade:
    """Walk future klines and determine the exit. Modifies trade in-place and returns it."""
    if not future_klines:
        trade.exit_time_ms = trade.entry_time_ms
        trade.exit_reason = "no_data"
        trade.pnl_pct = -_FEE
        return trade

    entry = trade.entry_price
    stop = trade.stop_loss
    tp1 = trade.take_profit_1
    tp2 = trade.take_profit_2
    direction = trade.direction
    tp1_filled = False

    for candle in future_klines[:max_candles]:
        if len(candle) < 5:
            continue
        o = float(candle[1])
        h = float(candle[2])
        lo = float(candle[3])
        ts = int(candle[0])

        if direction == "long":
            exit_px = o if o <= stop else stop if lo <= stop else None
            if exit_px is not None:
                trade.exit_time_ms = ts
                trade.exit_reason = "stop"
                trade.pnl_pct = (exit_px / entry - 1) - _FEE
                return trade
            if not tp1_filled and h >= tp1:
                tp1_filled = True
                if h >= tp2:
                    trade.exit_time_ms = ts
                    trade.exit_reason = "tp2"
                    trade.pnl_pct = 0.5 * (tp1 / entry - 1) + 0.5 * (tp2 / entry - 1) - _FEE
                    return trade
            elif tp1_filled and h >= tp2:
                trade.exit_time_ms = ts
                trade.exit_reason = "tp2"
                trade.pnl_pct = 0.5 * (tp1 / entry - 1) + 0.5 * (tp2 / entry - 1) - _FEE
                return trade

        else:  # short
            exit_px = o if o >= stop else stop if h >= stop else None
            if exit_px is not None:
                trade.exit_time_ms = ts
                trade.exit_reason = "stop"
                trade.pnl_pct = (entry / exit_px - 1) - _FEE
                return trade
            if not tp1_filled and lo <= tp1:
                tp1_filled = True
                if lo <= tp2:
                    trade.exit_time_ms = ts
                    trade.exit_reason = "tp2"
                    trade.pnl_pct = 0.5 * (entry / tp1 - 1) + 0.5 * (entry / tp2 - 1) - _FEE
                    return trade
            elif tp1_filled and lo <= tp2:
                trade.exit_time_ms = ts
                trade.exit_reason = "tp2"
                trade.pnl_pct = 0.5 * (entry / tp1 - 1) + 0.5 * (entry / tp2 - 1) - _FEE
                return trade

    last = future_klines[min(max_candles - 1, len(future_klines) - 1)]
    close = float(last[4])
    trade.exit_time_ms = int(last[0])

    if tp1_filled:
        trade.exit_reason = "tp1+timeout"
        if direction == "long":
            trade.pnl_pct = 0.5 * (tp1 / entry - 1) + 0.5 * (close / entry - 1) - _FEE
        else:
            trade.pnl_pct = 0.5 * (entry / tp1 - 1) + 0.5 * (entry / close - 1) - _FEE
    else:
        trade.exit_reason = "timeout"
        trade.pnl_pct = (close / entry - 1 if direction == "long" else entry / close - 1) - _FEE

    return trade
