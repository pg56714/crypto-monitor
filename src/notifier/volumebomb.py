import ccxt.async_support as ccxt
import asyncio
import polars as pl
from pathlib import Path

from src.core.discord import DiscordConnector
from src.core.config_reader import Config

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "src" / "config"
CONFIG_PATH = CONFIG_DIR / "notification.json"


class VolumeBomb(object):
    def __init__(self):
        self.discord = DiscordConnector()
        self.exchange = ccxt.binanceusdm()
        self.config = Config(CONFIG_PATH)["VolumeBomb"]
        self.timeframe = self.config.get("timeframe", "5m")

    async def run(self):
        """執行爆量檢查

        步驟：
        1. 取得K線資料
        2. 清理數據並生成平均成交量
        3. 檢查是否有爆量訊號
        """
        ohlcv_dict = await self.getKline()
        for symbol, ohlcv_df in ohlcv_dict.items():
            mean_volume = self.cleanData2GenerateMeanVolume(ohlcv_df)
            self.checkSignal(symbol, mean_volume, ohlcv_df)
        await self.exchange.close()

    async def getKline(self) -> dict:
        """取得K線資料（用async的方法取得多筆數據會較快）

        步驟：
        1. 取得K線資料
        2. 轉換成DataFrame以及對應的格式
        """
        ohlcv_dict = {}
        tasks = []

        async def get_ohlcv(symbol, timeframe):
            return await self.exchange.fetch_ohlcv(symbol, timeframe, limit=100)

        for symbol in self.config["valid_symbol"]:
            task = asyncio.create_task(get_ohlcv(symbol, self.timeframe))
            tasks.append(task)

        responses = await asyncio.gather(*tasks)
        for i, response in enumerate(responses):
            symbol = self.config["valid_symbol"][i]

            df = pl.DataFrame(response, schema=["time", "open", "high", "low", "close", "volume"])
            df = df.with_columns(
                [
                    pl.col("time").cast(pl.Int64),
                    pl.col("open").cast(pl.Float64),
                    pl.col("high").cast(pl.Float64),
                    pl.col("low").cast(pl.Float64),
                    pl.col("close").cast(pl.Float64),
                    pl.col("volume").cast(pl.Float64),
                ]
            )

            if symbol not in ohlcv_dict:
                ohlcv_dict[symbol] = {}
            ohlcv_dict[symbol] = df.slice(
                0, -1
            )  # 不取最後一筆資料，因為我們是每五分鐘的0秒開始偵測，最後一根K線才剛開始
        return ohlcv_dict

    def cleanData2GenerateMeanVolume(self, ohlcv_df):
        """清理數據並生成平均成交量

        步驟：
        1. 將成交量中的極端值去除
        2. 計算平均成交量
        """
        Q1 = ohlcv_df.select(pl.col("volume").quantile(0.25)).item()
        Q3 = ohlcv_df.select(pl.col("volume").quantile(0.75)).item()
        IQR = Q3 - Q1

        filtered_df = ohlcv_df.filter((pl.col("volume") >= Q1 - 1.5 * IQR) & (pl.col("volume") <= Q3 + 1.5 * IQR))
        mean_volume = filtered_df.select(pl.col("volume").mean()).item()
        return mean_volume

    def checkSignal(self, symbol, mean_volume, ohlcv_df):
        """檢查是否有爆量訊號

        步驟：
        1. 判斷趨勢
        2. 判斷成交量是否大於平均成交量的 10 倍
        """
        close_values = ohlcv_df.select(pl.col("close")).to_series()
        volume_values = ohlcv_df.select(pl.col("volume")).to_series()

        slope = close_values[-1] - close_values[-10]

        if slope <= 0:
            trend = "下跌"
        else:
            trend = "上漲"

        if volume_values[-1] >= mean_volume * 10:
            message = (
                f"```[🔥｜Volume Bomb] {symbol}爆量{trend}\n現價：{close_values[-1]}\n成交量：{volume_values[-1]}```"
            )
            self.discord.send_message("VOLUMEBOMB", message)
