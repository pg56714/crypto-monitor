"""Backtest five-factor scoring to compare signal frequency across thresholds."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from typing import Any

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from src.backtest.data import (
    SymbolData,
    fetch_server_time_ms,
    fetch_top_symbols,
    load_all,
    ms_per_candle,
)
from src.core.config_reader import Config
from src.core.paths import get_notification_config_path
from src.indicators.cvd import calculate_cvd_from_klines, direction_from_value
from src.indicators.funding import funding_direction
from src.indicators.long_short_ratio import long_short_ratio_direction
from src.indicators.open_interest import open_interest_direction
from src.scoring.five_factor import score_five_factor

_KLINE_WINDOW = 24
_OI_WINDOW = 48


def _latest_before(records: list[dict[str, Any]], ts_key: str, ts: int) -> dict[str, Any] | None:
    result = None
    for r in records:
        if int(r.get(ts_key, 0)) <= ts:
            result = r
        else:
            break
    return result


def _window_before(
    records: list[dict[str, Any]], ts_key: str, ts: int, n: int
) -> list[dict[str, Any]]:
    filtered = [r for r in records if int(r.get(ts_key, 0)) <= ts]
    return filtered[-n:]


def _simulate_symbol(
    data: SymbolData,
    start_ms: int,
    end_ms: int,
) -> list[int]:
    """Walk through time and compute score at each candle. Returns list of scores."""
    step = data.signal_step_ms

    klines_by_ts: dict[int, list[Any]] = {}
    for k in data.klines_signal:
        if isinstance(k, list) and k:
            klines_by_ts[int(k[0])] = k

    scores: list[int] = []
    ts = start_ms
    while ts < end_ms:
        window_klines = [
            klines_by_ts[ts - (_KLINE_WINDOW - 1 - i) * step]
            for i in range(_KLINE_WINDOW)
            if ts - (_KLINE_WINDOW - 1 - i) * step in klines_by_ts
        ]
        if len(window_klines) < 2:
            ts += step
            continue

        # Price direction
        prev_close = float(window_klines[-2][4])
        latest_close = float(window_klines[-1][4])
        dprice_dir = (
            direction_from_value(((latest_close - prev_close) / prev_close) * 100, threshold=0.3)
            if prev_close > 0
            else 0
        )

        # CVD
        cvd_dir = direction_from_value(calculate_cvd_from_klines(window_klines))

        # OI direction
        oi_window = _window_before(data.oi_hist_signal, "timestamp", ts + step - 1, _OI_WINDOW)
        oi_values = [
            float(r["sumOpenInterestValue"]) for r in oi_window if "sumOpenInterestValue" in r
        ]
        oi_dir, _, _ = open_interest_direction(oi_values)

        # Funding direction — compare current rate to one period prior
        candle_end = ts + step - 1
        curr_rec = _latest_before(data.funding_hist, "fundingTime", candle_end)
        if curr_rec:
            current_rate = float(curr_rec.get("fundingRate", 0.0) or 0.0)
            fund_ts = int(curr_rec.get("fundingTime", 0))
            prev_rec = _latest_before(data.funding_hist, "fundingTime", fund_ts - 1)
            previous_rate = (
                float(prev_rec.get("fundingRate", current_rate) or current_rate)
                if prev_rec
                else current_rate
            )
        else:
            current_rate = previous_rate = 0.0
        funding_dir, _ = funding_direction(current_rate, previous_rate)

        # LSR direction
        a = _latest_before(data.lsr_account, "timestamp", candle_end)
        p = _latest_before(data.lsr_position, "timestamp", candle_end)
        lsr_account_val = float(a.get("longShortRatio", 1.0) or 1.0) if a else 1.0
        lsr_position_val = float(p.get("longShortRatio", 1.0) or 1.0) if p else 1.0
        lsr_dir, _ = long_short_ratio_direction(lsr_account_val, lsr_position_val)

        result = score_five_factor(
            funding_dir=funding_dir,
            cvd_dir=cvd_dir,
            oi_dir=oi_dir,
            lsr_dir=lsr_dir,
            dprice_dir=dprice_dir,
        )
        scores.append(result.score)
        ts += step

    return scores


async def _run(
    *,
    days: int,
    symbols: list[str] | None,
    timeframe: str,
    top_n: int,
) -> None:
    step = ms_per_candle(timeframe)
    server_time_ms = await fetch_server_time_ms()
    local_time_ms = int(datetime.now(UTC).timestamp() * 1000)
    base_time_ms = server_time_ms if server_time_ms > 0 else local_time_ms
    end_ms = (base_time_ms // step) * step
    start_ms = end_ms - days * 24 * 3_600_000

    if not symbols:
        print(f"抓取前 {top_n} 大交易量幣種...")
        symbols = await fetch_top_symbols(top_n)
        print(f"幣種：{', '.join(symbols)}\n")

    print(f"下載資料：{len(symbols)} 個幣種，{days} 天，{timeframe} K 棒...\n")
    all_data = await load_all(
        symbols,
        start_ms=start_ms,
        end_ms=end_ms,
        daily_start_ms=start_ms,
        signal_timeframe=timeframe,
        include_five_factor=True,
        include_accumulation=False,
    )

    results: list[tuple[str, list[int]]] = []
    for symbol, data in all_data.items():
        scores = _simulate_symbol(data, start_ms, end_ms)
        print(f"  {symbol}: {len(scores)} 根 K 棒")
        results.append((symbol, scores))

    all_scores: list[int] = []
    symbol_scores: dict[str, list[int]] = {}
    for symbol, scores in results:
        if scores:
            all_scores.extend(scores)
            symbol_scores[symbol] = scores

    if not all_scores:
        print("\n沒有資料。")
        return

    total = len(all_scores)
    print(f"\n共 {total} 根 K 棒（{len(symbol_scores)} 個幣種）")
    print(f"\n{'閾值':>6}  {'多頭訊號':>10}  {'空頭訊號':>10}  {'合計':>8}  {'佔比':>8}")
    print("-" * 50)
    for threshold in [3, 4, 5, 6]:
        longs = sum(1 for s in all_scores if s >= threshold)
        shorts = sum(1 for s in all_scores if s <= -threshold)
        sig_total = longs + shorts
        pct = sig_total / total * 100
        print(f"{threshold:>6}  {longs:>10}  {shorts:>10}  {sig_total:>8}  {pct:>7.2f}%")

    print("\n分數分布（所有幣種合計）：")
    for score in range(-6, 7):
        count = sum(1 for s in all_scores if s == score)
        bar = "█" * (count * 40 // max(all_scores.count(s) for s in set(all_scores)))
        print(f"  {score:+d}: {count:6d}  {bar}")

    print("\n各幣種訊號數（閾值 ≥ 5）：")
    ranked = sorted(
        ((sym, sum(1 for s in sc if abs(s) >= 5)) for sym, sc in symbol_scores.items()),
        key=lambda x: -x[1],
    )
    for sym, count in ranked:
        if count > 0:
            print(f"  {sym}: {count}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回測五因子分數閾值")
    parser.add_argument("--days", type=int, default=7, help="回測天數（預設 7）")
    parser.add_argument("--symbols", nargs="+", help="指定幣種（不指定則取前 N 大）")
    parser.add_argument(
        "--timeframe",
        default=_default_timeframe(),
        help="K 棒週期（預設讀取 FiveFactor 設定）",
    )
    parser.add_argument("--top-n", type=int, default=20, help="取前 N 大交易量幣種（預設 20）")
    return parser.parse_args()


def _default_timeframe() -> str:
    config = Config(get_notification_config_path())
    five_factor = config.get("FiveFactor", {})
    if isinstance(five_factor, dict):
        return str(five_factor.get("timeframe", "5m"))
    return "5m"


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        _run(
            days=args.days,
            symbols=args.symbols,
            timeframe=args.timeframe,
            top_n=args.top_n,
        )
    )
