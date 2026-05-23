"""Accumulation follow-up scanner."""

import asyncio
import logging
from typing import Any

from src.clients.ai_summary import append_summary
from src.clients.binance import BinanceFuturesClient
from src.clients.coingecko import fetch_market_caps
from src.core.config_reader import Config
from src.core.discord import DiscordConnector
from src.core.paths import get_notification_config_path
from src.reports.accumulation import format_accumulation_scan
from src.scoring.accumulation import (
    score_ambush_signal,
    score_chase_signal,
    score_combined_signal,
)
from src.scoring.entry_engine import EntryPlan, build_entry_plan
from src.strategies.accumulation_pool import POOL

logger = logging.getLogger(__name__)

_TOP_N = 100
_MAX_CONCURRENCY = 10
_OI_LIMIT = 7


class AccumulationScanner:
    """Hourly OI-movement scanner scoring the accumulation pool and top market."""

    def __init__(self) -> None:
        notification_config = Config(get_notification_config_path())
        self.config: dict[str, Any] = notification_config.get("Accumulation", {})
        self.period: str = self.config.get("period", "1h")
        self.discord = DiscordConnector()

    async def run(self) -> None:
        """Scan pool + top symbols for OI moves, run the three scorers, notify."""
        if not self.config.get("enabled", False):
            return

        client = BinanceFuturesClient()
        try:
            tickers = await client.public_futures_get("/fapi/v1/ticker/24hr")
            market_caps = await self._safe_market_caps()
            ticker_map = self._ticker_map(tickers)
            symbols = self._select_symbols(ticker_map)
            semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
            rows = await asyncio.gather(
                *(
                    self._evaluate(client, symbol, ticker_map, market_caps, semaphore)
                    for symbol in symbols
                ),
                return_exceptions=True,
            )
        finally:
            await client.close()

        records = [row for row in rows if isinstance(row, dict)]
        chase = [r for s in records if (r := score_chase_signal(s)) is not None]
        combined = [r for s in records if (r := score_combined_signal(s)) is not None]
        ambush = [r for s in records if (r := score_ambush_signal(s)) is not None]
        for row in ambush:
            row["entry_plan"] = _entry_plan(row)
        message = format_accumulation_scan(chase=chase, combined=combined, ambush=ambush)
        if message:
            self.discord.send_message("ACCUMULATION", await append_summary(message))

    @staticmethod
    def _ticker_map(tickers: object) -> dict[str, dict[str, Any]]:
        """Index the 24h ticker payload by symbol."""
        if not isinstance(tickers, list):
            return {}
        return {
            str(item["symbol"]): item
            for item in tickers
            if isinstance(item, dict) and "symbol" in item
        }

    @staticmethod
    def _select_symbols(ticker_map: dict[str, dict[str, Any]]) -> list[str]:
        """Return pool symbols plus the top USDT perps by 24h quote volume."""
        usdt = [symbol for symbol in ticker_map if symbol.endswith("USDT")]
        usdt.sort(
            key=lambda symbol: float(ticker_map[symbol].get("quoteVolume", 0.0) or 0.0),
            reverse=True,
        )
        return list(dict.fromkeys([*POOL, *usdt[:_TOP_N]]))

    async def _safe_market_caps(self) -> dict[str, float]:
        """Fetch CoinGecko market caps, tolerating failure."""
        try:
            return await fetch_market_caps()
        except Exception:  # noqa: BLE001 - market cap is optional context
            logger.exception("AccumulationScanner: market cap fetch failed")
            return {}

    async def _evaluate(
        self,
        client: BinanceFuturesClient,
        symbol: str,
        ticker_map: dict[str, dict[str, Any]],
        market_caps: dict[str, float],
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any] | None:
        """Build the scorer input row for one symbol."""
        ticker = ticker_map.get(symbol)
        if ticker is None:
            return None
        async with semaphore:
            try:
                funding_pct = await self._funding_pct(client, symbol)
                oi_change_pct = await self._oi_change_pct(client, symbol)
            except Exception:  # noqa: BLE001 - isolate one symbol's failure from the scan
                logger.exception("AccumulationScanner: failed to scan %s", symbol)
                return None

        coin = symbol.replace("USDT", "")
        pool_entry = POOL.get(symbol)
        return {
            "symbol": symbol,
            "coin": coin,
            "px_chg": float(ticker.get("priceChangePercent", 0.0) or 0.0),
            "fr_pct": funding_pct,
            "vol": float(ticker.get("quoteVolume", 0.0) or 0.0),
            "est_mcap": market_caps.get(coin, 0.0),
            "sw_days": int(pool_entry["sideways_days"]) if pool_entry else 0,
            "d6h": oi_change_pct,
            "in_pool": pool_entry is not None,
            "support": float(pool_entry["low_price"]) if pool_entry else 0.0,
            "resistance": float(pool_entry["high_price"]) if pool_entry else 0.0,
            "vol_breakout": float(pool_entry["vol_breakout"]) if pool_entry else 0.0,
        }

    async def _funding_pct(self, client: BinanceFuturesClient, symbol: str) -> float:
        """Return the current funding rate as a percentage."""
        premium = await client.public_futures_get("/fapi/v1/premiumIndex", {"symbol": symbol})
        if isinstance(premium, dict):
            return float(premium.get("lastFundingRate", 0.0) or 0.0) * 100
        return 0.0

    async def _oi_change_pct(self, client: BinanceFuturesClient, symbol: str) -> float:
        """Return the open-interest percentage change over the recent window."""
        history = await client.public_futures_get(
            "/futures/data/openInterestHist",
            {"symbol": symbol, "period": self.period, "limit": _OI_LIMIT},
        )
        if not isinstance(history, list):
            return 0.0
        values = [
            float(row["sumOpenInterestValue"])
            for row in history
            if isinstance(row, dict) and "sumOpenInterestValue" in row
        ]
        if len(values) < 2 or values[0] <= 0:
            return 0.0
        return ((values[-1] - values[0]) / values[0]) * 100


def _entry_plan(row: dict[str, Any]) -> EntryPlan | None:
    """
    Build an entry plan from a pooled ambush candidate's price structure.

    The sideways window's low/high act as support/resistance, and its midpoint
    approximates the accumulation (whale) price. Volume breakout and rising OI
    stand in for the volume-spike and whale-inflow gates.
    """
    support = float(row.get("support", 0.0))
    resistance = float(row.get("resistance", 0.0))
    if support <= 0 or resistance <= 0:
        return None
    return build_entry_plan(
        avg_whale_price=(support + resistance) / 2,
        support=support,
        resistance=resistance,
        volume_spike=float(row.get("vol_breakout", 0.0)) >= 2.0,
        whale_inflow=float(row.get("d6h", 0.0)) > 0.0,
    )
