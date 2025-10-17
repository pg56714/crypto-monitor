"""Open interest notifier for Binance perpetual contracts."""

import asyncio
from typing import Any

import ccxt.async_support as ccxt
import polars as pl

from src.common.paths import get_notification_config_path
from src.core.config_reader import Config
from src.core.discord import DiscordConnector

OI_GROUP_DEFINITIONS: list[tuple[str, str, str]] = [
    (
        "up_up",
        "Funding UP & OI UP",
        "多頭槓桿累積，市場可能過熱，逐步減倉或設定止盈。",
    ),
    (
        "up_down",
        "Funding UP & OI DOWN",
        "多頭正在減倉，注意多頭擠壓，觀望或短空布局。",
    ),
    (
        "down_up",
        "Funding DOWN & OI UP",
        "空頭壓力增強，空頭擠壓的前兆，留意反彈機會或逢低佈局多單。",
    ),
    (
        "down_down",
        "Funding DOWN & OI DOWN",
        "多空都在減倉，市場參與度降低，暫時觀望或縮小倉位。",
    ),
]


class OI:
    """Monitor open interest changes and send concise alerts."""

    def __init__(self) -> None:
        self.discord = DiscordConnector()
        self.exchange = ccxt.binanceusdm()
        config: dict[str, Any] = Config(get_notification_config_path())
        self.config = config["OI"]
        self.threshold_pct: float = float(self.config.get("threshold_pct", 2.0))

    async def run(self) -> None:
        """Fetch the latest OI snapshot and dispatch notifications."""
        oi_df = await self.getOI()
        self.checkSignal(oi_df)
        await self.exchange.close()

    async def getOI(self) -> pl.DataFrame:
        """Collect OI metrics for all configured symbols."""
        symbols_config = self.config.get("valid_symbol")
        symbols = await self._resolve_symbols(symbols_config)

        timeframe = self.config.get("timeframe", "5m")
        if timeframe not in {
            "5m",
            "15m",
            "30m",
            "1h",
            "2h",
            "4h",
            "6h",
            "12h",
            "1d",
            "3d",
            "1w",
        }:
            timeframe = "5m"

        async def fetch_symbol(symbol: str) -> dict[str, float | str | None]:
            try:
                history = await self.exchange.fetch_open_interest_history(
                    symbol,
                    timeframe=timeframe,
                    limit=3,
                )
                latest_oi = self._extract_oi(history[-1] if history else None)
                prev_oi = self._extract_oi(history[-2]) if history and len(history) >= 2 else None
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
        except Exception:  # noqa: BLE001 - API may fail temporarily
            return []

        return [
            market["id"]
            for market in self.exchange.markets.values()
            if market.get("swap")
            and market.get("linear")
            and market.get("active")
            and market.get("quote") == "USDT"
        ]

    @staticmethod
    def _extract_oi(entry: dict[str, Any] | None) -> float | None:
        """Extract an open interest value from a CCXT response entry."""
        if entry is None:
            return None

        for key in ("openInterestValue",):
            value = entry.get(key)
            if value is not None:
                return float(value)

        info = entry.get("info")
        if isinstance(info, dict):
            for key in ("sumOpenInterestValue",):
                value = info.get(key)
                if value is not None:
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        continue

        return None

    @staticmethod
    def _classify_signal(oi_pct: float | None, funding_pct: float | None) -> str:
        """Categorize a row based on funding rate and OI delta signs."""
        if oi_pct is None or funding_pct is None:
            return "unknown"

        oi_up = oi_pct >= 0.0
        funding_up = funding_pct >= 0.0

        if funding_up and oi_up:
            return "up_up"
        if funding_up and not oi_up:
            return "up_down"
        if not funding_up and oi_up:
            return "down_up"
        return "down_down"

    def checkSignal(self, oi_df: pl.DataFrame) -> None:
        """Send grouped summaries when |dOI| exceeds the configured threshold."""
        if oi_df.is_empty():
            return

        df = oi_df.filter(pl.col("oi_pct").abs() >= self.threshold_pct)
        if df.is_empty():
            return

        df = df.sort("oi_pct", descending=True, nulls_last=True)
        header = (
            "```[OI ALERT] "
            f"(|dOI| >= {self.threshold_pct:.1f}%)\n"
            "SYMBOL        dOI(%)       FR(%)        PRICE"
        )

        groups = {key: [] for key, _, _ in OI_GROUP_DEFINITIONS}
        unknown: list[str] = []

        for row in df.iter_rows(named=True):
            symbol = row["symbol"]
            oi_pct = row.get("oi_pct")
            price_val = row["price"]
            fr_pct = row.get("funding_pct")

            pct_str = "N/A" if oi_pct is None else f"{oi_pct:+7.2f}%"
            fr_str = "N/A" if fr_pct is None else f"{fr_pct:+6.4f}%"
            price_str = "N/A" if price_val is None else f"{price_val:.4f}"
            line = f"{symbol:<10} {pct_str:<12} {fr_str:<12} {price_str}"

            category = self._classify_signal(oi_pct, fr_pct)
            if category in groups:
                groups[category].append(line)
            else:
                unknown.append(line)

        lines: list[str] = []
        for key, title, note in OI_GROUP_DEFINITIONS:
            bucket = groups.get(key, [])
            if not bucket:
                continue
            if lines:
                lines.append("")
            lines.append(title)
            lines.append(f"  {note}")
            lines.extend(bucket)

        if unknown:
            if lines:
                lines.append("")
            lines.append("Funding / OI N/A")
            lines.append("  Missing data; review manually.")
            lines.extend(unknown)

        self._send_chunked_messages(header, lines)

    def _send_chunked_messages(self, header: str, lines: list[str]) -> None:
        """Dispatch one or more Discord messages within the character limit."""
        if not lines:
            return

        max_chars = 1900
        footer = "```"
        base_len = len(header) + len(footer)
        chunks: list[list[str]] = []
        current: list[str] = []
        current_len = base_len

        for line in lines:
            addition = len(line) + 1  # account for newline when joining
            if current and current_len + addition > max_chars:
                chunks.append(current)
                current = []
                current_len = base_len

            current.append(line)
            current_len += addition

        if current:
            chunks.append(current)

        total_chunks = len(chunks)
        for idx, chunk in enumerate(chunks, start=1):
            page_header = header
            if total_chunks > 1:
                page_header = header.replace("```[", f"```[{idx}/{total_chunks}][", 1)
            message = "\n".join([page_header, *chunk, footer])
            self.discord.send_message("OI", message)
