"""Volume spike notifier for Binance perpetual contracts."""

import asyncio
from typing import Any

import ccxt.async_support as ccxt
import polars as pl

from src.common.paths import get_notification_config_path
from src.core.config_reader import Config
from src.core.discord import DiscordConnector


class VolumeBomb:
    """Detect sudden increases in trading volume."""

    def __init__(self) -> None:
        self.discord = DiscordConnector()
        self.exchange = ccxt.binanceusdm()
        config: dict[str, Any] = Config(get_notification_config_path()).get("VolumeBomb", {})
        self.config = config
        self.timeframe: str = config.get("timeframe", "5m")

    async def run(self) -> None:
        """Execute the volume spike detection workflow."""
        ohlcv_dict = await self.getKline()
        for symbol, ohlcv_df in ohlcv_dict.items():
            mean_volume = self.cleanData2GenerateMeanVolume(ohlcv_df)
            self.checkSignal(symbol, mean_volume, ohlcv_df)
        await self.exchange.close()

    async def getKline(self) -> dict[str, pl.DataFrame]:
        """Retrieve OHLCV data for configured symbols."""
        ohlcv_dict: dict[str, pl.DataFrame] = {}

        symbols_config = self.config.get("valid_symbol")
        symbols = await self._resolve_symbols(symbols_config)

        semaphore = asyncio.Semaphore(10)

        async def get_ohlcv(symbol: str, timeframe: str) -> list[list[float | int]]:
            async with semaphore:
                return await self.exchange.fetch_ohlcv(symbol, timeframe, limit=100)

        tasks = [asyncio.create_task(get_ohlcv(symbol, self.timeframe)) for symbol in symbols]

        responses = await asyncio.gather(*tasks)
        for index, response in enumerate(responses):
            symbol = symbols[index]
            df = pl.DataFrame(
                response,
                schema=["time", "open", "high", "low", "close", "volume"],
            ).with_columns(
                [
                    pl.col("time").cast(pl.Int64),
                    pl.col("open").cast(pl.Float64),
                    pl.col("high").cast(pl.Float64),
                    pl.col("low").cast(pl.Float64),
                    pl.col("close").cast(pl.Float64),
                    pl.col("volume").cast(pl.Float64),
                ]
            )

            ohlcv_dict[symbol] = df.slice(
                0, -1
            )  # Ignore the most recent bar because it is incomplete.
        return ohlcv_dict

    async def _resolve_symbols(self, symbols_config: dict[str, Any] | None) -> list[str]:
        """Expand configuration directives into specific trading symbols."""
        if not symbols_config:
            return []

        if isinstance(symbols_config, str):
            if symbols_config.upper() == "ALL":
                return await self._fetch_all_symbols()
            return [symbols_config]

        if isinstance(symbols_config, list):
            cleaned = [
                symbol for symbol in symbols_config if isinstance(symbol, str) and symbol.strip()
            ]
            if any(symbol.upper() == "ALL" for symbol in cleaned):
                return await self._fetch_all_symbols()
            return cleaned

        return []

    async def _fetch_all_symbols(self) -> list[str]:
        """Load all active linear USDT perpetual markets from the exchange."""
        try:
            await self.exchange.load_markets()
        except Exception:
            return []

        return [
            market["id"]
            for market in self.exchange.markets.values()
            if market.get("swap")
            and market.get("linear")
            and market.get("active")
            and market.get("quote") == "USDT"
        ]

    def cleanData2GenerateMeanVolume(self, ohlcv_df: pl.DataFrame) -> float:
        """Clean data and compute the mean trading volume."""
        q1 = ohlcv_df.select(pl.col("volume").quantile(0.25)).item()
        q3 = ohlcv_df.select(pl.col("volume").quantile(0.75)).item()
        iqr = q3 - q1

        filtered_df = ohlcv_df.filter(
            (pl.col("volume") >= q1 - 1.5 * iqr) & (pl.col("volume") <= q3 + 1.5 * iqr)
        )
        mean_volume = filtered_df.select(pl.col("volume").mean()).item()
        return float(mean_volume)

    def checkSignal(self, symbol: str, mean_volume: float, ohlcv_df: pl.DataFrame) -> None:
        """Inspect the latest candle and send a notification when the volume spikes."""
        close_values = ohlcv_df.select(pl.col("close")).to_series()
        volume_values = ohlcv_df.select(pl.col("volume")).to_series()

        slope = close_values[-1] - close_values[-10]
        trend = "上漲" if slope > 0 else "下跌"

        if volume_values[-1] >= mean_volume * 10:
            message = (
                "```[🔥｜Volume Bomb] "
                f"{symbol}爆量{trend}\n現價：{close_values[-1]}\n成交量：{volume_values[-1]}```"
            )
            self.discord.send_message("VOLUMEBOMB", message)
