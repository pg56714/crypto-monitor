"""Backtest five-factor scoring to compare signal frequency across thresholds."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from typing import Any

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

import aiohttp

from src.indicators.cvd import calculate_cvd_from_klines, direction_from_value
from src.indicators.funding import funding_direction
from src.indicators.long_short_ratio import long_short_ratio_direction
from src.indicators.open_interest import open_interest_direction
from src.scoring.five_factor import score_five_factor

_BASE_URL = "https://fapi.binance.com"
_KLINE_WINDOW = 24
_OI_WINDOW = 48
_MAX_CONCURRENCY = 5


async def _get(session: aiohttp.ClientSession, endpoint: str, params: dict[str, Any]) -> object:
    url = f"{_BASE_URL}{endpoint}"
    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as r:
        r.raise_for_status()
        return await r.json()


def _ms_per_candle(timeframe: str) -> int:
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    unit = timeframe[-1]
    count = int(timeframe[:-1])
    return count * units.get(unit, 3_600_000)


async def _fetch_symbol_data(
    session: aiohttp.ClientSession,
    symbol: str,
    timeframe: str,
    start_ms: int,
    end_ms: int,
) -> dict[str, list[Any]]:
    """Fetch all historical indicator data for one symbol in parallel."""
    step = _ms_per_candle(timeframe)
    fetch_start_ms = start_ms - (_OI_WINDOW + 10) * step

    klines, oi_hist, funding_hist, lsr_global, lsr_account, lsr_position = await asyncio.gather(
        _get(
            session,
            "/fapi/v1/klines",
            {
                "symbol": symbol,
                "interval": timeframe,
                "startTime": fetch_start_ms,
                "endTime": end_ms,
                "limit": 1500,
            },
        ),
        _get(
            session,
            "/futures/data/openInterestHist",
            {
                "symbol": symbol,
                "period": timeframe,
                "startTime": fetch_start_ms,
                "endTime": end_ms,
                "limit": 500,
            },
        ),
        _get(
            session,
            "/fapi/v1/fundingRate",
            {
                "symbol": symbol,
                "startTime": fetch_start_ms,
                "endTime": end_ms,
                "limit": 1000,
            },
        ),
        _get(
            session,
            "/futures/data/globalLongShortAccountRatio",
            {
                "symbol": symbol,
                "period": timeframe,
                "startTime": fetch_start_ms,
                "endTime": end_ms,
                "limit": 500,
            },
        ),
        _get(
            session,
            "/futures/data/topLongShortAccountRatio",
            {
                "symbol": symbol,
                "period": timeframe,
                "startTime": fetch_start_ms,
                "endTime": end_ms,
                "limit": 500,
            },
        ),
        _get(
            session,
            "/futures/data/topLongShortPositionRatio",
            {
                "symbol": symbol,
                "period": timeframe,
                "startTime": fetch_start_ms,
                "endTime": end_ms,
                "limit": 500,
            },
        ),
    )
    return {
        "klines": klines if isinstance(klines, list) else [],
        "oi_hist": oi_hist if isinstance(oi_hist, list) else [],
        "funding_hist": funding_hist if isinstance(funding_hist, list) else [],
        "lsr_global": lsr_global if isinstance(lsr_global, list) else [],
        "lsr_account": lsr_account if isinstance(lsr_account, list) else [],
        "lsr_position": lsr_position if isinstance(lsr_position, list) else [],
    }


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
    data: dict[str, list[Any]],
    timeframe: str,
    start_ms: int,
    end_ms: int,
) -> list[int]:
    """Walk through time and compute score at each candle. Returns list of scores."""
    step = _ms_per_candle(timeframe)

    klines_by_ts: dict[int, list[Any]] = {}
    for k in data["klines"]:
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
        oi_window = _window_before(data["oi_hist"], "timestamp", ts + step - 1, _OI_WINDOW)
        oi_values = [
            float(r["sumOpenInterestValue"]) for r in oi_window if "sumOpenInterestValue" in r
        ]
        oi_dir, _, _ = open_interest_direction(oi_values)

        # Funding direction — compare current rate to one period prior
        candle_end = ts + step - 1
        curr_rec = _latest_before(data["funding_hist"], "fundingTime", candle_end)
        if curr_rec:
            current_rate = float(curr_rec.get("fundingRate", 0.0) or 0.0)
            fund_ts = int(curr_rec.get("fundingTime", 0))
            prev_rec = _latest_before(data["funding_hist"], "fundingTime", fund_ts - 1)
            previous_rate = (
                float(prev_rec.get("fundingRate", current_rate) or current_rate)
                if prev_rec
                else current_rate
            )
        else:
            current_rate = previous_rate = 0.0
        funding_dir, _ = funding_direction(current_rate, previous_rate)

        # LSR direction
        a = _latest_before(data["lsr_account"], "timestamp", candle_end)
        p = _latest_before(data["lsr_position"], "timestamp", candle_end)
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


async def _fetch_top_symbols(session: aiohttp.ClientSession, n: int) -> list[str]:
    tickers = await _get(session, "/fapi/v1/ticker/24hr", {})
    if not isinstance(tickers, list):
        return []
    usdt = [t for t in tickers if isinstance(t, dict) and str(t.get("symbol", "")).endswith("USDT")]
    usdt.sort(key=lambda t: float(t.get("quoteVolume", 0) or 0), reverse=True)
    return [str(t["symbol"]) for t in usdt[:n]]


async def _run(
    *,
    days: int,
    symbols: list[str] | None,
    timeframe: str,
    top_n: int,
) -> None:
    now = datetime.now(UTC)
    step = _ms_per_candle(timeframe)
    end_ms = (int(now.timestamp() * 1000) // step) * step
    start_ms = end_ms - days * 24 * 3_600_000
    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

    async with aiohttp.ClientSession() as session:
        if not symbols:
            print(f"抓取前 {top_n} 大交易量幣種...")
            symbols = await _fetch_top_symbols(session, top_n)
            print(f"幣種：{', '.join(symbols)}\n")

        async def process(symbol: str) -> tuple[str, list[int]]:
            async with semaphore:
                try:
                    data = await _fetch_symbol_data(session, symbol, timeframe, start_ms, end_ms)
                    scores = _simulate_symbol(data, timeframe, start_ms, end_ms)
                except Exception as exc:
                    print(f"  ✗ {symbol}: {exc}")
                    return symbol, []
                else:
                    print(f"  ✓ {symbol}: {len(scores)} 根 K 棒")
                    return symbol, scores

        print(f"回測中：{len(symbols)} 個幣種，{days} 天，{timeframe} K 棒...\n")
        results = await asyncio.gather(*(process(s) for s in symbols))

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
    parser.add_argument("--timeframe", default="1h", help="K 棒週期（預設 1h）")
    parser.add_argument("--top-n", type=int, default=20, help="取前 N 大交易量幣種（預設 20）")
    return parser.parse_args()


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
