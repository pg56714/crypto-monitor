"""Historical data fetching for backtest."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import aiohttp

_BASE_URL = "https://fapi.binance.com"
_MAX_CONCURRENCY = 5


@dataclass
class SymbolData:
    """Historical market data for one symbol, fetched for backtesting."""

    symbol: str
    klines_1h: list[list[Any]] = field(default_factory=list)
    klines_1d: list[list[Any]] = field(default_factory=list)
    oi_hist_1h: list[dict[str, Any]] = field(default_factory=list)
    funding_hist: list[dict[str, Any]] = field(default_factory=list)
    lsr_global: list[dict[str, Any]] = field(default_factory=list)
    lsr_account: list[dict[str, Any]] = field(default_factory=list)
    lsr_position: list[dict[str, Any]] = field(default_factory=list)


async def _get(session: aiohttp.ClientSession, endpoint: str, params: dict[str, Any]) -> object:
    url = f"{_BASE_URL}{endpoint}"
    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as r:
        r.raise_for_status()
        return await r.json()


async def _fetch_symbol(
    session: aiohttp.ClientSession,
    symbol: str,
    start_ms: int,
    end_ms: int,
    daily_start_ms: int,
) -> SymbolData:
    results = await asyncio.gather(
        _get(
            session,
            "/fapi/v1/klines",
            {
                "symbol": symbol,
                "interval": "1h",
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": 1500,
            },
        ),
        _get(
            session,
            "/fapi/v1/klines",
            {
                "symbol": symbol,
                "interval": "1d",
                "startTime": daily_start_ms,
                "endTime": end_ms,
                "limit": 1500,
            },
        ),
        _get(
            session,
            "/futures/data/openInterestHist",
            {
                "symbol": symbol,
                "period": "1h",
                "endTime": end_ms,
                "limit": 500,
            },
        ),
        _get(
            session,
            "/fapi/v1/fundingRate",
            {
                "symbol": symbol,
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": 1000,
            },
        ),
        _get(
            session,
            "/futures/data/globalLongShortAccountRatio",
            {
                "symbol": symbol,
                "period": "1h",
                "endTime": end_ms,
                "limit": 500,
            },
        ),
        _get(
            session,
            "/futures/data/topLongShortAccountRatio",
            {
                "symbol": symbol,
                "period": "1h",
                "endTime": end_ms,
                "limit": 500,
            },
        ),
        _get(
            session,
            "/futures/data/topLongShortPositionRatio",
            {
                "symbol": symbol,
                "period": "1h",
                "endTime": end_ms,
                "limit": 500,
            },
        ),
        return_exceptions=True,
    )

    def _safe(result: object) -> list[Any]:
        return result if isinstance(result, list) else []

    return SymbolData(
        symbol=symbol,
        klines_1h=_safe(results[0]),
        klines_1d=_safe(results[1]),
        oi_hist_1h=_safe(results[2]),
        funding_hist=_safe(results[3]),
        lsr_global=_safe(results[4]),
        lsr_account=_safe(results[5]),
        lsr_position=_safe(results[6]),
    )


async def load_all(
    symbols: list[str],
    *,
    start_ms: int,
    end_ms: int,
    daily_start_ms: int,
) -> dict[str, SymbolData]:
    """Fetch all historical data for the given symbols in parallel."""
    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

    async with aiohttp.ClientSession() as session:

        async def fetch(symbol: str) -> tuple[str, SymbolData | None]:
            async with semaphore:
                try:
                    data = await _fetch_symbol(session, symbol, start_ms, end_ms, daily_start_ms)
                except Exception as exc:
                    print(f"  ✗ {symbol}: {exc}")
                    return symbol, None
                else:
                    print(f"  ✓ {symbol}: {len(data.klines_1h)} 1h / {len(data.klines_1d)} 1d")
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
