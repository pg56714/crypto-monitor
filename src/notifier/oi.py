import ccxt.async_support as ccxt
import asyncio
import polars as pl
from pathlib import Path

from src.core.discord import DiscordConnector
from src.core.config_reader import Config


ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "src" / "config"
CONFIG_PATH = CONFIG_DIR / "notification.json"


class OI(object):
    def __init__(self):
        self.discord = DiscordConnector()
        self.exchange = ccxt.binanceusdm()
        self.config = Config(CONFIG_PATH)["OI"]

    async def run(self):
        """取得各品種的最新 OI 與價格並發送通知"""
        oi_df = await self.getOI()
        self.checkSignal(oi_df)
        await self.exchange.close()

    async def getOI(self) -> pl.DataFrame:
        """並行取得多個商品的最新 OI 與價格與變化率"""
        symbols_config = self.config.get("valid_symbol")
        # 若未提供或為空，或指定為 "ALL"，則抓取所有 USDT 永續合約之交易對
        if not symbols_config or (isinstance(symbols_config, str) and symbols_config.upper() == "ALL"):
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
            except Exception:
                symbols = []
        else:
            symbols = symbols_config
        timeframe = self.config.get("timeframe", "5m")

        async def fetch_symbol(symbol):
            # 取得 OI 歷史後取最後一筆作為最新值
            try:
                history = await self.exchange.fetch_open_interest_history(symbol, timeframe=timeframe, limit=3)
                latest_oi = history[-1]["openInterest"] if history else None
                prev_oi = history[-2]["openInterest"] if history and len(history) >= 2 else None
            except Exception:
                latest_oi = None
                prev_oi = None

            oi_pct = None
            if latest_oi is not None and prev_oi not in (None, 0):
                try:
                    oi_pct = (latest_oi - prev_oi) / prev_oi * 100.0
                except Exception:
                    oi_pct = None

            last_price = None
            try:
                ticker = await self.exchange.fetch_ticker(symbol)
                last_price = ticker.get("last")
            except Exception:
                pass

            funding_pct = None
            try:
                fr = await self.exchange.fetch_funding_rate(symbol)
                rate = fr.get("fundingRate")
                if rate is not None:
                    funding_pct = rate * 100.0
            except Exception:
                pass

            return {
                "symbol": symbol,
                "oi": latest_oi,
                "oi_pct": oi_pct,
                "price": last_price,
                "funding_pct": funding_pct,
            }

        # 控制並發，避免過度打爆交易所 API
        semaphore = asyncio.Semaphore(10)

        async def limited_fetch(s):
            async with semaphore:
                return await fetch_symbol(s)

        tasks = [asyncio.create_task(limited_fetch(s)) for s in symbols]
        results = await asyncio.gather(*tasks)
        df = pl.DataFrame(
            results,
            schema={
                "symbol": pl.Utf8,
                "oi": pl.Float64,
                "oi_pct": pl.Float64,
                "price": pl.Float64,
                "funding_pct": pl.Float64,
            },
        )
        return df

    def checkSignal(self, oi_df: pl.DataFrame):
        """只在 |ΔOI| >= 1.5% 的品項時送出精簡列表，沒有觸發則不發"""
        if oi_df.is_empty():
            return

        df = oi_df.filter(pl.col("oi_pct").abs() >= 1.5)
        if df.is_empty():
            return

        df = df.sort("oi_pct", descending=True, nulls_last=True)
        header = "```[📊｜OI 異常偵測] (|Δ| ≥ 1.5%)\nSYMBOL        OI            ΔOI(%)       FR(%)     PRICE"
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
                lines.append(f"{symbol:<8}    {oi_val:>12.0f}   {pct_str:<12} {fr_str:<8} {price_val}")
        message = "\n".join([header] + lines + ["```"])
        self.discord.send_message("OI", message)
