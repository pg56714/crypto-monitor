"""Trade dataclass and candle-by-candle exit simulation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_FEE = 0.001  # 0.1% round trip (0.05% each side)
_PARTIAL_SIZE = 0.5


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
                if tp1_filled:
                    trade.exit_reason = "tp1+stop"
                    trade.pnl_pct = _partial_long_pnl(entry, tp1, exit_px)
                else:
                    trade.exit_reason = "stop"
                    trade.pnl_pct = (exit_px / entry - 1) - _FEE
                return trade
            if not tp1_filled and h >= tp1:
                tp1_filled = True
                if h >= tp2:
                    trade.exit_time_ms = ts
                    trade.exit_reason = "tp2"
                    trade.pnl_pct = _partial_long_pnl(entry, tp1, tp2)
                    return trade
            elif tp1_filled and h >= tp2:
                trade.exit_time_ms = ts
                trade.exit_reason = "tp2"
                trade.pnl_pct = _partial_long_pnl(entry, tp1, tp2)
                return trade

        else:  # short
            exit_px = o if o >= stop else stop if h >= stop else None
            if exit_px is not None:
                trade.exit_time_ms = ts
                if tp1_filled:
                    trade.exit_reason = "tp1+stop"
                    trade.pnl_pct = _partial_short_pnl(entry, tp1, exit_px)
                else:
                    trade.exit_reason = "stop"
                    trade.pnl_pct = _short_pnl(entry, exit_px)
                return trade
            if not tp1_filled and lo <= tp1:
                tp1_filled = True
                if lo <= tp2:
                    trade.exit_time_ms = ts
                    trade.exit_reason = "tp2"
                    trade.pnl_pct = _partial_short_pnl(entry, tp1, tp2)
                    return trade
            elif tp1_filled and lo <= tp2:
                trade.exit_time_ms = ts
                trade.exit_reason = "tp2"
                trade.pnl_pct = _partial_short_pnl(entry, tp1, tp2)
                return trade

    last = future_klines[min(max_candles - 1, len(future_klines) - 1)]
    close = float(last[4])
    trade.exit_time_ms = int(last[0])

    if tp1_filled:
        trade.exit_reason = "tp1+timeout"
        if direction == "long":
            trade.pnl_pct = _partial_long_pnl(entry, tp1, close)
        else:
            trade.pnl_pct = _partial_short_pnl(entry, tp1, close)
    else:
        trade.exit_reason = "timeout"
        trade.pnl_pct = (
            (close / entry - 1) - _FEE if direction == "long" else _short_pnl(entry, close)
        )

    return trade


def _partial_long_pnl(entry: float, first_exit: float, final_exit: float) -> float:
    return (
        _PARTIAL_SIZE * (first_exit / entry - 1) + _PARTIAL_SIZE * (final_exit / entry - 1) - _FEE
    )


def _partial_short_pnl(entry: float, first_exit: float, final_exit: float) -> float:
    return (
        _PARTIAL_SIZE * (1 - first_exit / entry) + _PARTIAL_SIZE * (1 - final_exit / entry) - _FEE
    )


def _short_pnl(entry: float, exit_price: float) -> float:
    return (1 - exit_price / entry) - _FEE
