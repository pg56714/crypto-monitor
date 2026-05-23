"""CoinGecko public API helpers."""

import aiohttp


async def fetch_market_caps(*, pages: int = 3) -> dict[str, float]:
    """Fetch a symbol -> USD market-cap map from CoinGecko."""
    caps: dict[str, float] = {}
    url = "https://api.coingecko.com/api/v3/coins/markets"
    async with aiohttp.ClientSession() as session:
        for page in range(1, pages + 1):
            params = {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 250,
                "page": page,
            }
            async with session.get(url, params=params, timeout=15) as response:
                response.raise_for_status()
                payload = await response.json()
            if not isinstance(payload, list) or not payload:
                break
            for item in payload:
                if not isinstance(item, dict):
                    continue
                symbol = item.get("symbol")
                market_cap = item.get("market_cap")
                if not isinstance(symbol, str) or not isinstance(market_cap, (int, float)):
                    continue
                if market_cap > 0:
                    caps.setdefault(symbol.upper(), float(market_cap))
    return caps
