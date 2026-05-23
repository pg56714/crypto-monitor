"""Accumulation pool scanner."""

import asyncio
import logging
from typing import Any

from src.clients.ai_summary import append_summary
from src.clients.binance import BinanceFuturesClient
from src.core.config_reader import Config
from src.core.discord import DiscordConnector
from src.core.paths import get_notification_config_path
from src.indicators.volatility import range_pct
from src.reports.accumulation import format_accumulation_pool

EXCLUDED_COINS = {"USDC", "USDP", "TUSD", "FDUSD", "BTCDOM", "DEFI", "USDM"}
logger = logging.getLogger(__name__)

# Latest pool scan, shared with AccumulationScanner (single-process state).
POOL: dict[str, dict[str, Any]] = {}


def analyze_accumulation(
    symbol: str,
    klines: list[list[float | int]],
    *,
    min_data_days: int = 90,
    min_sideways_days: int = 45,
    max_range_pct: float = 80.0,
    max_avg_vol_usd: float = 50_000_000,
    volume_breakout_multiple: float = 2.0,
) -> dict[str, Any] | None:
    """Analyze one symbol for accumulation characteristics."""
    if len(klines) < min_data_days:
        return None

    coin = symbol.replace("USDT", "")
    if coin in EXCLUDED_COINS:
        return None

    rows = [_normalize_daily_kline(row) for row in klines]
    recent_7d = rows[-7:]
    prior = rows[:-7]
    if not prior:
        return None

    recent_avg_px = sum(row["close"] for row in recent_7d) / len(recent_7d)
    prior_avg_px = sum(row["close"] for row in prior) / len(prior)
    if prior_avg_px > 0 and ((recent_avg_px - prior_avg_px) / prior_avg_px) > 3.0:
        return None

    best = _find_best_sideways_window(
        prior,
        min_sideways_days=min_sideways_days,
        max_range_pct=max_range_pct,
        max_avg_vol_usd=max_avg_vol_usd,
    )
    if best is None:
        return None

    recent_vol = sum(row["vol"] for row in recent_7d) / len(recent_7d)
    vol_breakout = recent_vol / best["avg_vol"] if best["avg_vol"] > 0 else 0
    total_score = _score_pool_candidate(
        sideways_days=int(best["sideways_days"]),
        range_value=float(best["range_pct"]),
        avg_vol=float(best["avg_vol"]),
        vol_breakout=vol_breakout,
        max_range_pct=max_range_pct,
        max_avg_vol_usd=max_avg_vol_usd,
        volume_breakout_multiple=volume_breakout_multiple,
        current_price=rows[-1]["close"],
    )

    return {
        "symbol": symbol,
        "coin": coin,
        "sideways_days": best["sideways_days"],
        "range_pct": best["range_pct"],
        "low_price": best["low_price"],
        "high_price": best["high_price"],
        "avg_vol": best["avg_vol"],
        "current_price": rows[-1]["close"],
        "recent_vol": recent_vol,
        "vol_breakout": vol_breakout,
        "score": total_score,
        "data_days": len(rows),
    }


def _normalize_daily_kline(row: list[float | int]) -> dict[str, float]:
    return {
        "open": float(row[1]),
        "high": float(row[2]),
        "low": float(row[3]),
        "close": float(row[4]),
        "vol": float(row[7]),
    }


def _find_best_sideways_window(
    rows: list[dict[str, float]],
    *,
    min_sideways_days: int,
    max_range_pct: float,
    max_avg_vol_usd: float,
) -> dict[str, float] | None:
    best: dict[str, float] | None = None
    for window in range(min_sideways_days, len(rows) + 1):
        window_rows = rows[-window:]
        lows = [row["low"] for row in window_rows]
        highs = [row["high"] for row in window_rows]
        low_price = min(lows)
        high_price = max(highs)
        window_range_pct = range_pct(low_price, high_price)
        avg_vol = sum(row["vol"] for row in window_rows) / len(window_rows)
        if window_range_pct > max_range_pct or avg_vol > max_avg_vol_usd:
            continue
        if best is None or window > best["sideways_days"]:
            best = {
                "sideways_days": float(window),
                "range_pct": window_range_pct,
                "low_price": low_price,
                "high_price": high_price,
                "avg_vol": avg_vol,
            }
    return best


def _score_pool_candidate(
    *,
    sideways_days: int,
    range_value: float,
    avg_vol: float,
    vol_breakout: float,
    max_range_pct: float,
    max_avg_vol_usd: float,
    volume_breakout_multiple: float,
    current_price: float,
) -> float:
    days_score = min(sideways_days / 90, 1.0) * 25
    range_score = max(0.0, (1 - range_value / max_range_pct)) * 20
    vol_score = max(0.0, (1 - avg_vol / max_avg_vol_usd)) * 20
    breakout_score = min(vol_breakout / volume_breakout_multiple, 1.0) * 15
    estimated_mcap = current_price * avg_vol * 30
    mcap_score = 20 if 0 < estimated_mcap < 50_000_000 else 0
    return days_score + range_score + vol_score + breakout_score + mcap_score


class AccumulationPool:
    """Daily accumulation-pool scanner for Binance USDT perpetuals."""

    def __init__(self) -> None:
        notification_config = Config(get_notification_config_path())
        self.config: dict[str, Any] = notification_config.get("Accumulation", {})
        self.timeframe: str = self.config.get("timeframe", "1d")
        self.lookback_days: int = int(self.config.get("lookback_days", 180))
        self.min_sideways_days: int = int(self.config.get("min_sideways_days", 45))
        self.discord = DiscordConnector()

    async def run(self) -> None:
        """Scan USDT perpetuals for accumulation candidates and notify Discord."""
        if not self.config.get("enabled", False):
            return

        client = BinanceFuturesClient()
        semaphore = asyncio.Semaphore(10)
        try:
            symbols = await client.fetch_all_usdt_perp_symbols()
            scanned = await asyncio.gather(
                *(self._scan_symbol(client, symbol, semaphore) for symbol in symbols),
                return_exceptions=True,
            )
        finally:
            await client.close()

        results = [item for item in scanned if isinstance(item, dict)]
        results.sort(key=lambda item: float(item["score"]), reverse=True)
        POOL.clear()
        POOL.update({str(item["symbol"]): item for item in results})
        message = await append_summary(format_accumulation_pool(results))
        self.discord.send_message("ACCUMULATION", message)

    async def _scan_symbol(
        self,
        client: BinanceFuturesClient,
        symbol: str,
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any] | None:
        """Fetch one symbol's daily klines and analyze it for accumulation."""
        async with semaphore:
            try:
                klines = await client.public_futures_get(
                    "/fapi/v1/klines",
                    {"symbol": symbol, "interval": self.timeframe, "limit": self.lookback_days},
                )
                if not isinstance(klines, list):
                    return None
                return analyze_accumulation(
                    symbol, klines, min_sideways_days=self.min_sideways_days
                )
            except Exception:  # noqa: BLE001 - isolate one symbol's failure from the scan
                logger.exception("AccumulationPool: failed to scan %s", symbol)
                return None
