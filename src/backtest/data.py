"""Historical data fetching for backtest."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiohttp

from src.core.paths import ROOT

_BASE_URL = "https://fapi.binance.com"
_MAX_CONCURRENCY = 2
_MAX_KLINE_LIMIT = 1500
_MAX_DATA_LIMIT = 500
_MAX_FUNDING_LIMIT = 1000
_SIGNAL_LOOKBACK_CANDLES = 48
_HOURLY_LOOKBACK_MS = 24 * 3_600_000
_FUTURES_DATA_LOOKBACK_MS = 29 * 86_400_000
_RETRY_STATUSES = {418, 429, 500, 502, 503, 504}
_MAX_RETRIES = 4
_CACHE_DIR = ROOT / "backtest_output" / "cache"


@dataclass
class SymbolData:
    """Historical market data for one symbol, fetched for backtesting."""

    symbol: str
    signal_timeframe: str = "1h"
    signal_step_ms: int = 3_600_000
    klines_signal: list[list[Any]] = field(default_factory=list)
    oi_hist_signal: list[dict[str, Any]] = field(default_factory=list)
    klines_1h: list[list[Any]] = field(default_factory=list)
    klines_1d: list[list[Any]] = field(default_factory=list)
    oi_hist_1h: list[dict[str, Any]] = field(default_factory=list)
    funding_hist: list[dict[str, Any]] = field(default_factory=list)
    lsr_global: list[dict[str, Any]] = field(default_factory=list)
    lsr_account: list[dict[str, Any]] = field(default_factory=list)
    lsr_position: list[dict[str, Any]] = field(default_factory=list)


async def _get(session: aiohttp.ClientSession, endpoint: str, params: dict[str, Any]) -> object:
    url = f"{_BASE_URL}{endpoint}"
    for attempt in range(_MAX_RETRIES):
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as r:
            if r.status in _RETRY_STATUSES and attempt < _MAX_RETRIES - 1:
                await r.read()
                await asyncio.sleep(_retry_delay_seconds(attempt, r.headers.get("Retry-After")))
                continue
            r.raise_for_status()
            return await r.json()
    raise RuntimeError(f"Failed to fetch {endpoint}")


def _retry_delay_seconds(attempt: int, retry_after: str | None) -> float:
    if retry_after is not None:
        try:
            return max(1.0, float(retry_after))
        except ValueError:
            pass
    return min(2.0 * (attempt + 1), 8.0)


def ms_per_candle(timeframe: str) -> int:
    """Return the candle duration in milliseconds for Binance-style intervals."""
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    unit = timeframe[-1]
    count = int(timeframe[:-1])
    return count * units[unit]


async def _get_paginated(
    session: aiohttp.ClientSession,
    endpoint: str,
    params: dict[str, Any],
    *,
    start_ms: int,
    end_ms: int,
    limit: int,
    timestamp: Callable[[Any], int],
) -> list[Any]:
    records: list[Any] = []
    cursor = start_ms
    while cursor <= end_ms:
        request_end_ms = min(end_ms, cursor + _page_span_ms(limit, params.get("period")))
        payload = await _get(
            session,
            endpoint,
            {**params, "startTime": cursor, "endTime": request_end_ms, "limit": limit},
        )
        if not isinstance(payload, list) or not payload:
            break

        page = [item for item in payload if timestamp(item) > 0]
        if not page:
            break
        records.extend(page)

        last_ts = max(timestamp(item) for item in page)
        next_cursor = last_ts + 1
        if request_end_ms >= end_ms or next_cursor <= cursor:
            break
        cursor = next_cursor

    return _dedupe_by_timestamp(records, timestamp)


async def _get_cached_paginated(
    session: aiohttp.ClientSession,
    endpoint: str,
    params: dict[str, Any],
    *,
    start_ms: int,
    end_ms: int,
    limit: int,
    timestamp: Callable[[Any], int],
) -> list[Any]:
    cache_path = _cache_path(endpoint, params, start_ms=start_ms, end_ms=end_ms, limit=limit)
    cached = _read_cache(cache_path)
    if cached is not None:
        return cached

    records = await _get_paginated(
        session,
        endpoint,
        params,
        start_ms=start_ms,
        end_ms=end_ms,
        limit=limit,
        timestamp=timestamp,
    )
    _write_cache(cache_path, records)
    return records


def _cache_path(
    endpoint: str, params: dict[str, Any], *, start_ms: int, end_ms: int, limit: int
) -> Path:
    payload = {
        "endpoint": endpoint,
        "params": params,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "limit": limit,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    symbol = str(params.get("symbol", "global"))
    return _CACHE_DIR / symbol / f"{digest}.json"


def _read_cache(path: Path) -> list[Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, list) else None


def _write_cache(path: Path, records: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, separators=(",", ":")), encoding="utf-8")


def _page_span_ms(limit: int, period: object) -> int:
    if isinstance(period, str):
        return max(ms_per_candle(period), (limit - 1) * ms_per_candle(period))
    return 30 * 86_400_000


def _dedupe_by_timestamp(records: list[Any], timestamp: Callable[[Any], int]) -> list[Any]:
    deduped: dict[int, Any] = {}
    for record in records:
        ts = timestamp(record)
        if ts > 0:
            deduped[ts] = record
    return [deduped[ts] for ts in sorted(deduped)]


def _list_timestamp(row: object) -> int:
    return int(row[0]) if isinstance(row, list) and row else 0


def _dict_timestamp(row: object) -> int:
    return int(row.get("timestamp", 0)) if isinstance(row, dict) else 0


def _funding_timestamp(row: object) -> int:
    return int(row.get("fundingTime", 0)) if isinstance(row, dict) else 0


async def _fetch_symbol(
    session: aiohttp.ClientSession,
    symbol: str,
    start_ms: int,
    end_ms: int,
    daily_start_ms: int,
    signal_timeframe: str,
    include_five_factor: bool,
    include_accumulation: bool,
) -> SymbolData:
    signal_step_ms = ms_per_candle(signal_timeframe)
    signal_start_ms = start_ms - (_SIGNAL_LOOKBACK_CANDLES * signal_step_ms)
    hourly_start_ms = start_ms - _HOURLY_LOOKBACK_MS
    futures_data_floor_ms = end_ms - _FUTURES_DATA_LOOKBACK_MS
    signal_data_start_ms = max(signal_start_ms, futures_data_floor_ms)
    hourly_data_start_ms = max(hourly_start_ms, futures_data_floor_ms)
    indicator_start_ms = min(signal_start_ms, hourly_start_ms)

    data = SymbolData(
        symbol=symbol,
        signal_timeframe=signal_timeframe,
        signal_step_ms=signal_step_ms,
    )

    tasks: dict[str, Awaitable[list[Any]]] = {}
    if include_five_factor:
        tasks["klines_signal"] = _get_cached_paginated(
            session,
            "/fapi/v1/klines",
            {
                "symbol": symbol,
                "interval": signal_timeframe,
            },
            start_ms=signal_start_ms,
            end_ms=end_ms,
            limit=_MAX_KLINE_LIMIT,
            timestamp=_list_timestamp,
        )
        tasks["oi_hist_signal"] = _get_cached_paginated(
            session,
            "/futures/data/openInterestHist",
            {
                "symbol": symbol,
                "period": signal_timeframe,
            },
            start_ms=signal_data_start_ms,
            end_ms=end_ms,
            limit=_MAX_DATA_LIMIT,
            timestamp=_dict_timestamp,
        )
        tasks["lsr_global"] = _get_cached_paginated(
            session,
            "/futures/data/globalLongShortAccountRatio",
            {
                "symbol": symbol,
                "period": signal_timeframe,
            },
            start_ms=signal_data_start_ms,
            end_ms=end_ms,
            limit=_MAX_DATA_LIMIT,
            timestamp=_dict_timestamp,
        )
        tasks["lsr_account"] = _get_cached_paginated(
            session,
            "/futures/data/topLongShortAccountRatio",
            {
                "symbol": symbol,
                "period": signal_timeframe,
            },
            start_ms=signal_data_start_ms,
            end_ms=end_ms,
            limit=_MAX_DATA_LIMIT,
            timestamp=_dict_timestamp,
        )
        tasks["lsr_position"] = _get_cached_paginated(
            session,
            "/futures/data/topLongShortPositionRatio",
            {
                "symbol": symbol,
                "period": signal_timeframe,
            },
            start_ms=signal_data_start_ms,
            end_ms=end_ms,
            limit=_MAX_DATA_LIMIT,
            timestamp=_dict_timestamp,
        )

    if include_accumulation:
        if not (include_five_factor and signal_timeframe == "1h"):
            tasks["klines_1h"] = _get_cached_paginated(
                session,
                "/fapi/v1/klines",
                {
                    "symbol": symbol,
                    "interval": "1h",
                },
                start_ms=hourly_start_ms,
                end_ms=end_ms,
                limit=_MAX_KLINE_LIMIT,
                timestamp=_list_timestamp,
            )
            tasks["oi_hist_1h"] = _get_cached_paginated(
                session,
                "/futures/data/openInterestHist",
                {
                    "symbol": symbol,
                    "period": "1h",
                },
                start_ms=hourly_data_start_ms,
                end_ms=end_ms,
                limit=_MAX_DATA_LIMIT,
                timestamp=_dict_timestamp,
            )
        tasks["klines_1d"] = _get_cached_paginated(
            session,
            "/fapi/v1/klines",
            {
                "symbol": symbol,
                "interval": "1d",
            },
            start_ms=daily_start_ms,
            end_ms=end_ms,
            limit=_MAX_KLINE_LIMIT,
            timestamp=_list_timestamp,
        )

    if include_five_factor or include_accumulation:
        tasks["funding_hist"] = _get_cached_paginated(
            session,
            "/fapi/v1/fundingRate",
            {
                "symbol": symbol,
            },
            start_ms=indicator_start_ms,
            end_ms=end_ms,
            limit=_MAX_FUNDING_LIMIT,
            timestamp=_funding_timestamp,
        )

    keys = list(tasks)
    values = await asyncio.gather(*(tasks[key] for key in keys))
    for key, value in zip(keys, values, strict=True):
        setattr(data, key, value)

    if include_accumulation and include_five_factor and signal_timeframe == "1h":
        data.klines_1h = data.klines_signal
        data.oi_hist_1h = data.oi_hist_signal

    if include_accumulation and not include_five_factor:
        data.klines_signal = data.klines_1h
        data.oi_hist_signal = data.oi_hist_1h

    return data


async def load_all(
    symbols: list[str],
    *,
    start_ms: int,
    end_ms: int,
    daily_start_ms: int,
    signal_timeframe: str = "1h",
    include_five_factor: bool = True,
    include_accumulation: bool = True,
) -> dict[str, SymbolData]:
    """Fetch all historical data for the given symbols in parallel."""
    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

    async with aiohttp.ClientSession() as session:

        async def fetch(symbol: str) -> tuple[str, SymbolData | None]:
            async with semaphore:
                try:
                    data = await _fetch_symbol(
                        session,
                        symbol,
                        start_ms,
                        end_ms,
                        daily_start_ms,
                        signal_timeframe,
                        include_five_factor,
                        include_accumulation,
                    )
                except Exception as exc:
                    print(f"  ERR {symbol}: {exc}")
                    return symbol, None
                else:
                    print(
                        f"  OK {symbol}: {len(data.klines_signal)} {signal_timeframe} / "
                        f"{len(data.klines_1h)} 1h / {len(data.klines_1d)} 1d"
                    )
                    return symbol, data

        results = await asyncio.gather(*(fetch(s) for s in symbols))

    return {s: d for s, d in results if d is not None}


async def fetch_top_symbols(n: int) -> list[str]:
    """Return the top-n USDT perpetuals by 24h quote volume."""
    async with aiohttp.ClientSession() as session:
        tickers = await _get(session, "/fapi/v1/ticker/24hr", {})
    if not isinstance(tickers, list):
        return []
    usdt = [t for t in tickers if isinstance(t, dict) and str(t.get("symbol", "")).endswith("USDT")]
    usdt.sort(key=lambda t: float(t.get("quoteVolume", 0) or 0), reverse=True)
    return [str(t["symbol"]) for t in usdt[:n]]


async def fetch_server_time_ms() -> int:
    """Return Binance USD-M futures server time in milliseconds."""
    async with aiohttp.ClientSession() as session:
        payload = await _get(session, "/fapi/v1/time", {})
    if isinstance(payload, dict):
        return int(payload.get("serverTime", 0) or 0)
    return 0
