"""Five-factor backtest: candle-by-candle signal generation and trade simulation."""

from __future__ import annotations

import bisect
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.backtest.data import SymbolData
from src.backtest.trade import Trade, simulate_trade
from src.indicators.cvd import calculate_cvd_from_klines, direction_from_value
from src.indicators.funding import funding_direction
from src.indicators.long_short_ratio import long_short_ratio_direction
from src.indicators.open_interest import open_interest_direction
from src.scoring.five_factor import score_five_factor

_KLINE_WINDOW = 24
_OI_WINDOW = 48
_ENTRY_SCORE_MIN = 4
_MAX_HOLD_MS = 72 * 3_600_000
_FALLBACK_STOP_PCT = 0.015
_MAX_STOP_PCT = 0.08


def run_five_factor_backtest(
    data: SymbolData,
    *,
    start_ms: int,
    end_ms: int,
    dedup_hours: int = 4,
    session_timezone: str = "UTC",
    session_start_hour: int | None = None,
    session_end_hour: int | None = None,
) -> list[Trade]:
    """Walk historical signal-timeframe data and simulate five-factor trades."""
    klines_by_ts: dict[int, list[Any]] = {}
    for k in data.klines_signal:
        if isinstance(k, list) and k:
            klines_by_ts[int(k[0])] = k

    sorted_ts = sorted(klines_by_ts)
    sorted_klines = [klines_by_ts[t] for t in sorted_ts]
    step_ms = data.signal_step_ms
    dedup_ms = dedup_hours * 3_600_000
    max_hold_candles = max(1, _MAX_HOLD_MS // step_ms)

    trades: list[Trade] = []
    last_alert: dict[str, int] = {}

    ts = start_ms
    while ts < end_ms:
        window = [
            klines_by_ts[ts - (_KLINE_WINDOW - 1 - i) * step_ms]
            for i in range(_KLINE_WINDOW)
            if ts - (_KLINE_WINDOW - 1 - i) * step_ms in klines_by_ts
        ]
        if len(window) < 2:
            ts += step_ms
            continue

        dprice_dir = _price_direction(window)
        cvd_dir = direction_from_value(calculate_cvd_from_klines(window))

        candle_end = ts + step_ms - 1
        oi_window = _window_before(data.oi_hist_signal, "timestamp", candle_end, _OI_WINDOW)
        oi_values = [
            float(r["sumOpenInterestValue"]) for r in oi_window if "sumOpenInterestValue" in r
        ]
        oi_dir, _, _ = open_interest_direction(oi_values)

        funding_dir = _funding_direction(data.funding_hist, candle_end)
        lsr_dir = _lsr_direction(data.lsr_account, data.lsr_position, candle_end)

        result = score_five_factor(
            funding_dir=funding_dir,
            cvd_dir=cvd_dir,
            oi_dir=oi_dir,
            lsr_dir=lsr_dir,
            dprice_dir=dprice_dir,
        )

        if abs(result.score) >= _ENTRY_SCORE_MIN:
            direction = "long" if result.score > 0 else "short"
            if (
                _in_session(
                    ts,
                    timezone=session_timezone,
                    start_hour=session_start_hour,
                    end_hour=session_end_hour,
                )
                and ts - last_alert.get(direction, 0) >= dedup_ms
            ):
                entry_ts = ts + step_ms
                entry_kline = klines_by_ts.get(entry_ts)
                if entry_kline is not None:
                    entry_price = float(entry_kline[1])
                    plan = _build_plan(window, entry_price, direction)
                    if plan is not None:
                        idx = bisect.bisect_left(sorted_ts, entry_ts)
                        trade = Trade(
                            symbol=data.symbol,
                            strategy="five_factor",
                            direction=direction,
                            entry_time_ms=entry_ts,
                            entry_price=entry_price,
                            stop_loss=plan["stop_loss"],
                            take_profit_1=plan["take_profit_1"],
                            take_profit_2=plan["take_profit_2"],
                        )
                        simulate_trade(trade, sorted_klines[idx:], max_candles=max_hold_candles)
                        trades.append(trade)
                        last_alert[direction] = ts

        ts += step_ms

    return trades


def _in_session(
    ts_ms: int,
    *,
    timezone: str,
    start_hour: int | None,
    end_hour: int | None,
) -> bool:
    if start_hour is None and end_hour is None:
        return True
    if start_hour is None or end_hour is None:
        return True

    hour = datetime.fromtimestamp(ts_ms / 1000, UTC).astimezone(ZoneInfo(timezone)).hour
    if start_hour == end_hour:
        return True
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def _price_direction(window: list[list[Any]]) -> int:
    prev_close = float(window[-2][4])
    latest_close = float(window[-1][4])
    if prev_close <= 0:
        return 0
    change_pct = ((latest_close - prev_close) / prev_close) * 100
    return direction_from_value(change_pct, threshold=0.3)


def _window_before(
    records: list[dict[str, Any]], ts_key: str, ts: int, n: int
) -> list[dict[str, Any]]:
    filtered = [r for r in records if int(r.get(ts_key, 0)) <= ts]
    return filtered[-n:]


def _latest_before(records: list[dict[str, Any]], ts_key: str, ts: int) -> dict[str, Any] | None:
    result = None
    for r in records:
        if int(r.get(ts_key, 0)) <= ts:
            result = r
        else:
            break
    return result


def _funding_direction(funding_hist: list[dict[str, Any]], candle_end: int) -> int:
    curr = _latest_before(funding_hist, "fundingTime", candle_end)
    if curr is None:
        return 0
    current_rate = float(curr.get("fundingRate", 0.0) or 0.0)
    fund_ts = int(curr.get("fundingTime", 0))
    prev = _latest_before(funding_hist, "fundingTime", fund_ts - 1)
    previous_rate = (
        float(prev.get("fundingRate", current_rate) or current_rate) if prev else current_rate
    )
    direction, _ = funding_direction(current_rate, previous_rate)
    return direction


def _lsr_direction(
    lsr_account: list[dict[str, Any]], lsr_position: list[dict[str, Any]], candle_end: int
) -> int:
    a = _latest_before(lsr_account, "timestamp", candle_end)
    p = _latest_before(lsr_position, "timestamp", candle_end)
    acc = float(a.get("longShortRatio", 1.0) or 1.0) if a else 1.0
    pos = float(p.get("longShortRatio", 1.0) or 1.0) if p else 1.0
    direction, _ = long_short_ratio_direction(acc, pos)
    return direction


def _build_plan(
    window: list[list[Any]], entry_price: float, direction: str
) -> dict[str, float] | None:
    lows = [float(k[3]) for k in window if len(k) > 3 and float(k[3]) > 0]
    highs = [float(k[2]) for k in window if len(k) > 2 and float(k[2]) > 0]
    if not lows or not highs:
        return None

    if direction == "long":
        structural = min(lows)
        risk_pct = (entry_price - structural) / entry_price
        stop = (
            structural if 0 < risk_pct <= _MAX_STOP_PCT else entry_price * (1 - _FALLBACK_STOP_PCT)
        )
        risk = entry_price - stop
        if risk <= 0:
            return None
        return {
            "stop_loss": stop,
            "take_profit_1": entry_price + risk * 2,
            "take_profit_2": entry_price + risk * 3,
        }
    else:
        structural = max(highs)
        risk_pct = (structural - entry_price) / entry_price
        stop = (
            structural if 0 < risk_pct <= _MAX_STOP_PCT else entry_price * (1 + _FALLBACK_STOP_PCT)
        )
        risk = stop - entry_price
        if risk <= 0:
            return None
        tp1 = entry_price - risk * 2
        tp2 = entry_price - risk * 3
        if tp1 <= 0 or tp2 <= 0:
            return None
        return {"stop_loss": stop, "take_profit_1": tp1, "take_profit_2": tp2}
