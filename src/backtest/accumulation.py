"""Accumulation pool + scanner backtest."""

from __future__ import annotations

import bisect
from typing import Any

from src.backtest.data import SymbolData
from src.backtest.trade import Trade, simulate_trade
from src.scoring.accumulation import score_ambush_signal
from src.strategies.accumulation_pool import analyze_accumulation

_OI_WINDOW = 7
_MAX_HOLD_CANDLES = 240
_STEP_MS = 3_600_000
_DAY_MS = 86_400_000
_STOP_BUFFER = 0.03
_TP2_MULTIPLIER = 1.2


def run_accumulation_backtest(data: SymbolData, *, start_ms: int, end_ms: int) -> list[Trade]:
    """Walk historical data and simulate accumulation ambush trades for one symbol."""
    klines_1h_by_ts: dict[int, list[Any]] = {}
    for k in data.klines_1h:
        if isinstance(k, list) and k:
            klines_1h_by_ts[int(k[0])] = k

    klines_1d_by_ts: dict[int, list[Any]] = {}
    for k in data.klines_1d:
        if isinstance(k, list) and k:
            klines_1d_by_ts[int(k[0])] = k

    sorted_ts_1h = sorted(klines_1h_by_ts)
    sorted_klines_1h = [klines_1h_by_ts[t] for t in sorted_ts_1h]

    trades: list[Trade] = []
    pool_cache: dict[int, dict[str, Any] | None] = {}

    ts = start_ms
    while ts < end_ms:
        day_ts = (ts // _DAY_MS) * _DAY_MS
        if day_ts not in pool_cache:
            daily = sorted(
                [k for t, k in klines_1d_by_ts.items() if t < day_ts],
                key=lambda k: int(k[0]),
            )
            pool_cache[day_ts] = analyze_accumulation(data.symbol, daily)

        pool_entry = pool_cache[day_ts]
        if pool_entry is None:
            ts += _STEP_MS
            continue

        # Don't enter while a prior trade is still open
        if trades and trades[-1].exit_time_ms is not None and trades[-1].exit_time_ms > ts:
            ts += _STEP_MS
            continue

        kline = klines_1h_by_ts.get(ts)
        if kline is None:
            ts += _STEP_MS
            continue

        current_price = float(kline[4])
        if current_price <= 0:
            ts += _STEP_MS
            continue

        candle_end = ts + _STEP_MS - 1
        d6h = _compute_d6h(data.oi_hist_1h, candle_end)
        fr_pct = _compute_fr_pct(data.funding_hist, candle_end)
        px_chg = _compute_px_chg(klines_1h_by_ts, ts)
        avg_vol = float(pool_entry["avg_vol"])

        scorer_input: dict[str, Any] = {
            "symbol": data.symbol,
            "coin": data.symbol.replace("USDT", ""),
            "in_pool": True,
            "px_chg": px_chg,
            "fr_pct": fr_pct,
            "vol": float(kline[7]) if len(kline) > 7 else 0.0,
            "est_mcap": current_price * avg_vol * 30,
            "sw_days": int(pool_entry["sideways_days"]),
            "d6h": d6h,
            "support": float(pool_entry["low_price"]),
            "resistance": float(pool_entry["high_price"]),
            "vol_breakout": float(pool_entry["vol_breakout"]),
        }

        signal = score_ambush_signal(scorer_input)
        if signal is not None:
            entry_ts = ts + _STEP_MS
            entry_kline = klines_1h_by_ts.get(entry_ts)
            if entry_kline is not None:
                entry_price = float(entry_kline[1])
                support = float(pool_entry["low_price"])
                resistance = float(pool_entry["high_price"])
                stop_loss = support * (1 - _STOP_BUFFER)
                tp1 = resistance
                tp2 = resistance * _TP2_MULTIPLIER
                if entry_price > 0 and stop_loss > 0 and tp1 > entry_price and tp2 > tp1:
                    idx = bisect.bisect_left(sorted_ts_1h, entry_ts)
                    trade = Trade(
                        symbol=data.symbol,
                        strategy="accumulation",
                        direction="long",
                        entry_time_ms=entry_ts,
                        entry_price=entry_price,
                        stop_loss=stop_loss,
                        take_profit_1=tp1,
                        take_profit_2=tp2,
                    )
                    simulate_trade(trade, sorted_klines_1h[idx:], max_candles=_MAX_HOLD_CANDLES)
                    trades.append(trade)

        ts += _STEP_MS

    return trades


def _compute_d6h(oi_hist: list[dict[str, Any]], candle_end: int) -> float:
    window = [r for r in oi_hist if int(r.get("timestamp", 0)) <= candle_end][-_OI_WINDOW:]
    values = [float(r["sumOpenInterestValue"]) for r in window if "sumOpenInterestValue" in r]
    if len(values) < 2 or values[0] <= 0:
        return 0.0
    return ((values[-1] - values[0]) / values[0]) * 100


def _compute_fr_pct(funding_hist: list[dict[str, Any]], candle_end: int) -> float:
    result = None
    for r in funding_hist:
        if int(r.get("fundingTime", 0)) <= candle_end:
            result = r
        else:
            break
    if result is None:
        return 0.0
    return float(result.get("fundingRate", 0.0) or 0.0) * 100


def _compute_px_chg(klines_by_ts: dict[int, list[Any]], ts: int) -> float:
    current = klines_by_ts.get(ts)
    prev = klines_by_ts.get(ts - 24 * _STEP_MS)
    if current is None or prev is None:
        return 0.0
    current_close = float(current[4])
    prev_close = float(prev[4])
    if prev_close <= 0:
        return 0.0
    return ((current_close - prev_close) / prev_close) * 100
