"""Binance futures client helpers."""

import aiohttp
import ccxt.async_support as ccxt


class BinanceFuturesClient:
    """Wrap ccxt and Binance public futures endpoints."""

    def __init__(self) -> None:
        self.exchange = ccxt.binanceusdm()

    async def close(self) -> None:
        """Close the underlying ccxt session."""
        await self.exchange.close()

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        *,
        limit: int = 100,
    ) -> list[list[float | int]]:
        """Fetch OHLCV candles through ccxt."""
        return await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

    async def fetch_all_usdt_perp_symbols(self) -> list[str]:
        """Load all active linear USDT perpetual symbols."""
        await self.exchange.load_markets()
        return [
            market["id"]
            for market in self.exchange.markets.values()
            if market.get("swap")
            and market.get("linear")
            and market.get("active")
            and market.get("quote") == "USDT"
        ]

    async def public_futures_get(
        self,
        endpoint: str,
        params: dict[str, str | int | float] | None = None,
    ) -> object:
        """Call a Binance USD-M futures public endpoint with aiohttp."""
        url = f"https://fapi.binance.com{endpoint}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as response:
                response.raise_for_status()
                return await response.json()
