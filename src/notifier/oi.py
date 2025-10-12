"""Open interest notifier for Binance perpetual contracts."""

import asyncio
from typing import Any

import ccxt.async_support as ccxt
import polars as pl

from src.common.paths import get_notification_config_path
from src.core.config_reader import Config
from src.core.discord import DiscordConnector


class OI:
    """Monitor open interest changes and send concise alerts."""

    def __init__(self) -> None:
        self.discord = DiscordConnector()
        self.exchange = ccxt.binanceusdm()
        config: dict[str, Any] = Config(get_notification_config_path())
        self.config = config["OI"]
        self.threshold_pct: float = float(self.config.get("threshold_pct", 1.0))

    async def run(self) -> None:
        """Fetch the latest OI snapshot and dispatch notifications."""
        oi_df = await self.getOI()
        self.checkSignal(oi_df)
        await self.exchange.close()

    async def getOI(self) -> pl.DataFrame:
        """Collect OI metrics for all configured symbols."""
        symbols_config = self.config.get("valid_symbol")
        if not symbols_config or (
            isinstance(symbols_config, str) and symbols_config.upper() == "ALL"
        ):
            try:
                await self.exchange.load_markets()
                symbols = [
                    market["id"]
                    for market in self.exchange.markets.values()
                    if market.get("swap")
                    and market.get("linear")
                    and market.get("active")
                    and market.get("quote") == "USDT"
                ]
            except Exception:  # noqa: BLE001 - fall back to empty list when API fails
                symbols = []
        else:
            symbols = symbols_config

        timeframe = self.config.get("timeframe", "5m")

        async def fetch_symbol(symbol: str) -> dict[str, float | str | None]:
            try:
                history = await self.exchange.fetch_open_interest_history(
                    symbol,
                    timeframe=timeframe,
                    limit=3,
                )
                latest_oi = history[-1]["openInterest"] if history else None
                prev_oi = history[-2]["openInterest"] if history and len(history) >= 2 else None
            except Exception:  # noqa: BLE001 - API reliability varies
                latest_oi = None
                prev_oi = None

            oi_pct: float | None = None
            if latest_oi is not None and prev_oi not in (None, 0):
                try:
                    oi_pct = (latest_oi - prev_oi) / prev_oi * 100.0
                except Exception:  # noqa: BLE001 - guard division/precision issues
                    oi_pct = None

            try:
                ticker = await self.exchange.fetch_ticker(symbol)
                last_price = ticker.get("last")
            except Exception:  # noqa: BLE001 - non-critical transport errors
                last_price = None

            try:
                funding_rate = await self.exchange.fetch_funding_rate(symbol)
                rate = funding_rate.get("fundingRate")
                funding_pct = rate * 100.0 if rate is not None else None
            except Exception:  # noqa: BLE001 - funding endpoint may not be available
                funding_pct = None

            return {
                "symbol": symbol,
                "oi": latest_oi,
                "oi_pct": oi_pct,
                "price": last_price,
                "funding_pct": funding_pct,
            }

        semaphore = asyncio.Semaphore(10)

        async def limited_fetch(symbol: str) -> dict[str, float | str | None]:
            async with semaphore:
                return await fetch_symbol(symbol)

        tasks = [asyncio.create_task(limited_fetch(symbol)) for symbol in symbols]
        results = await asyncio.gather(*tasks)
        return pl.DataFrame(
            results,
            schema={
                "symbol": pl.Utf8,
                "oi": pl.Float64,
                "oi_pct": pl.Float64,
                "price": pl.Float64,
                "funding_pct": pl.Float64,
            },
        )

    def checkSignal(self, oi_df: pl.DataFrame) -> None:
        """Send a summary when |ΔOI| exceeds the configured threshold."""
        if oi_df.is_empty():
            return

        df = oi_df.filter(pl.col("oi_pct").abs() >= self.threshold_pct)
        if df.is_empty():
            return

        df = df.sort("oi_pct", descending=True, nulls_last=True)
        header = (
            "```[📊｜OI 異常偵測] "
            f"(|Δ| ≥ {self.threshold_pct:.1f}%)\n"
            "SYMBOL        OI            ΔOI(%)       FR(%)     PRICE"
        )
        lines = []
        for row in df.iter_rows(named=True):
            symbol = row["symbol"]
            oi_val = row["oi"]
            oi_pct = row.get("oi_pct")
            price_val = row["price"]
            fr_pct = row.get("funding_pct")
            arrow = "" if oi_pct is None else ("🔼" if oi_pct >= 0 else "🔽")
            pct_str = "N/A" if oi_pct is None else f"{oi_pct:>7.2f}{arrow}"
            fr_str = "N/A" if fr_pct is None else f"{fr_pct:>6.4f}"
            if oi_val is None:
                lines.append(f"{symbol:<8}    N/A           {pct_str:<12} {fr_str:<8} {price_val}")
            else:
                lines.append(
                    f"{symbol:<8}    {oi_val:>12.0f}   {pct_str:<12} {fr_str:<8} {price_val}"
                )
        message = "\n".join([header, *lines, "```"])
        self.discord.send_message("OI", message)
