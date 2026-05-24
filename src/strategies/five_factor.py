"""Five-factor futures signal strategy."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.clients.binance import BinanceFuturesClient
from src.core.config_reader import Config
from src.core.discord import DiscordConnector
from src.core.paths import get_notification_config_path
from src.indicators.cvd import calculate_cvd_from_klines, direction_from_value
from src.indicators.funding import funding_direction
from src.indicators.long_short_ratio import long_short_ratio_direction
from src.indicators.open_interest import open_interest_direction
from src.reports.five_factor import format_five_factor_alert
from src.scoring.five_factor import detect_patterns, score_five_factor

logger = logging.getLogger(__name__)

# The scheduler runs in one long-lived process, so module-level state persists
# between cron invocations: previous funding rates and the dedup history.
_funding_snapshot: dict[str, float] = {}
_alert_history: dict[tuple[str, str], datetime] = {}

_MAX_CONCURRENCY = 10
_KLINE_LIMIT = 24
_OI_LIMIT = 48
_ENTRY_SCORE_MIN = 4
_ENTRY_ZONE_PCT = 0.001
_FALLBACK_STOP_PCT = 0.015
_MAX_STOP_PCT = 0.08


class FiveFactor:
    """Scan USDT perpetuals for OI/Funding/CVD/LSR/ΔPrice combination signals."""

    def __init__(self) -> None:
        self.config: dict[str, Any] = Config(get_notification_config_path()).get("FiveFactor", {})
        self.timeframe: str = self.config.get("timeframe", "5m")
        self.min_volume_usdt: float = float(self.config.get("min_volume_usdt", 5_000_000))
        self.dedup_hours: int = int(self.config.get("dedup_hours", 4))
        self.discord = DiscordConnector()

    async def run(self) -> None:
        """Scan markets and push five-factor signals to Discord."""
        if not self.config.get("enabled", False):
            return

        client = BinanceFuturesClient()
        try:
            symbols = await self._resolve_symbols(client)
            if not symbols:
                logger.info("FiveFactor: no symbols passed the volume filter.")
                return
            semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
            scanned = await asyncio.gather(
                *(self._scan_symbol(client, symbol, semaphore) for symbol in symbols),
                return_exceptions=True,
            )
        finally:
            await client.close()

        signals = [item for item in scanned if isinstance(item, dict)]
        if not signals:
            logger.info("FiveFactor: no signals cleared the threshold.")
            return

        message = format_five_factor_alert(signals)
        if message:
            self.discord.send_message("FIVE_FACTOR", message)
            now = datetime.now(UTC)
            for signal in signals:
                _alert_history[(str(signal["symbol"]), str(signal["direction"]))] = now

    async def _resolve_symbols(self, client: BinanceFuturesClient) -> list[str]:
        """Return symbols passing the configured 24h quote-volume filter."""
        configured = self.config.get("valid_symbol", ["ALL"])
        if isinstance(configured, list) and "ALL" not in configured:
            return [symbol for symbol in configured if isinstance(symbol, str)]

        symbols = await client.fetch_all_usdt_perp_symbols()
        tickers = await client.public_futures_get("/fapi/v1/ticker/24hr")
        if not isinstance(tickers, list):
            return []
        volume_by_symbol = {
            str(ticker.get("symbol")): float(ticker.get("quoteVolume", 0.0) or 0.0)
            for ticker in tickers
            if isinstance(ticker, dict)
        }
        return [
            symbol
            for symbol in symbols
            if volume_by_symbol.get(symbol, 0.0) >= self.min_volume_usdt
        ]

    async def _scan_symbol(
        self,
        client: BinanceFuturesClient,
        symbol: str,
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any] | None:
        """Evaluate one symbol, skipping recent alerts and isolating errors."""
        async with semaphore:
            try:
                signal = await self._evaluate_symbol(client, symbol)
            except Exception:  # noqa: BLE001 - isolate one symbol's failure from the scan
                logger.exception("FiveFactor: failed to scan %s", symbol)
                return None
        if signal is None:
            return None
        if self._recently_alerted(symbol, str(signal["direction"])):
            return None
        return signal

    def _recently_alerted(self, symbol: str, direction: str) -> bool:
        """Return True when the symbol was alerted within the dedup window."""
        last = _alert_history.get((symbol, direction))
        if last is None:
            return False
        return datetime.now(UTC) - last < timedelta(hours=self.dedup_hours)

    async def _evaluate_symbol(
        self, client: BinanceFuturesClient, symbol: str
    ) -> dict[str, Any] | None:
        """Fetch every factor for a symbol and build a signal when it scores."""
        klines = await client.public_futures_get(
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": self.timeframe, "limit": _KLINE_LIMIT},
        )
        if not isinstance(klines, list) or len(klines) < 2:
            return None

        dprice_dir = self._price_direction(klines)
        cvd = calculate_cvd_from_klines(klines)
        cvd_dir = direction_from_value(cvd)
        oi_dir, oi_change_pct = await self._open_interest(client, symbol)
        funding_rate, funding_dir, mark_price = await self._funding(client, symbol)
        lsr_global, lsr_account, lsr_position, lsr_dir = await self._long_short(client, symbol)
        current_price = mark_price if mark_price > 0 else self._latest_close(klines)

        result = score_five_factor(
            funding_dir=funding_dir,
            cvd_dir=cvd_dir,
            oi_dir=oi_dir,
            lsr_dir=lsr_dir,
            dprice_dir=dprice_dir,
        )
        if abs(result.score) < _ENTRY_SCORE_MIN:
            return None
        direction = "long" if result.score > 0 else "short"

        patterns = detect_patterns(
            funding_rate=funding_rate,
            oi_dir=oi_dir,
            cvd_dir=cvd_dir,
            dprice_dir=dprice_dir,
            lsr_global=lsr_global,
            lsr_account=lsr_account,
            lsr_position=lsr_position,
        )
        return {
            "symbol": symbol,
            "timeframe": self.timeframe,
            "score": result.score,
            "verdict": result.verdict,
            "direction": direction,
            "patterns": patterns,
            "current_price": current_price,
            "trade_plan": _build_trade_plan(
                klines=klines,
                current_price=current_price,
                direction=direction,
            ),
            "funding_rate": funding_rate,
            "oi_change_pct": oi_change_pct,
            "cvd": cvd,
            "lsr_global": lsr_global,
        }

    @staticmethod
    def _price_direction(klines: list[list[Any]]) -> int:
        """Return the price direction from the last two candle closes."""
        previous_close = float(klines[-2][4])
        latest_close = float(klines[-1][4])
        if previous_close <= 0:
            return 0
        change_pct = ((latest_close - previous_close) / previous_close) * 100
        return direction_from_value(change_pct, threshold=0.3)

    @staticmethod
    def _latest_close(klines: list[list[Any]]) -> float:
        """Return the latest kline close price."""
        if not klines:
            return 0.0
        return float(klines[-1][4])

    async def _open_interest(self, client: BinanceFuturesClient, symbol: str) -> tuple[int, float]:
        """Return the open-interest direction and percentage change."""
        history = await client.public_futures_get(
            "/futures/data/openInterestHist",
            {"symbol": symbol, "period": self.timeframe, "limit": _OI_LIMIT},
        )
        if not isinstance(history, list):
            return 0, 0.0
        values = [
            float(row["sumOpenInterestValue"])
            for row in history
            if isinstance(row, dict) and "sumOpenInterestValue" in row
        ]
        direction, change_pct, _segments = open_interest_direction(values)
        return direction, change_pct

    async def _funding(self, client: BinanceFuturesClient, symbol: str) -> tuple[float, int, float]:
        """Return the current funding rate, direction, and mark price."""
        premium = await client.public_futures_get("/fapi/v1/premiumIndex", {"symbol": symbol})
        current = 0.0
        mark_price = 0.0
        if isinstance(premium, dict):
            current = float(premium.get("lastFundingRate", 0.0) or 0.0)
            mark_price = float(premium.get("markPrice", 0.0) or 0.0)
        previous = _funding_snapshot.get(symbol, current)
        _funding_snapshot[symbol] = current
        direction, _label = funding_direction(current, previous)
        return current, direction, mark_price

    async def _long_short(
        self, client: BinanceFuturesClient, symbol: str
    ) -> tuple[float, float, float, int]:
        """Return global/account/position long-short ratios and the LSR direction."""
        global_ratio = await self._latest_ratio(
            client, "/futures/data/globalLongShortAccountRatio", symbol
        )
        account_ratio = await self._latest_ratio(
            client, "/futures/data/topLongShortAccountRatio", symbol
        )
        position_ratio = await self._latest_ratio(
            client, "/futures/data/topLongShortPositionRatio", symbol
        )
        direction, _label = long_short_ratio_direction(account_ratio, position_ratio)
        return global_ratio, account_ratio, position_ratio, direction

    async def _latest_ratio(
        self, client: BinanceFuturesClient, endpoint: str, symbol: str
    ) -> float:
        """Return the most recent long-short ratio from a Binance data endpoint."""
        data = await client.public_futures_get(
            endpoint, {"symbol": symbol, "period": self.timeframe, "limit": 1}
        )
        if isinstance(data, list) and data and isinstance(data[-1], dict):
            return float(data[-1].get("longShortRatio", 1.0) or 1.0)
        return 1.0


def _build_trade_plan(
    *,
    klines: list[list[Any]],
    current_price: float,
    direction: str,
) -> dict[str, Any] | None:
    """Build a simple market-entry plan from recent swing highs and lows."""
    if current_price <= 0 or direction not in {"long", "short"}:
        return None
    lows = [_safe_float(row[3]) for row in klines if len(row) > 3]
    highs = [_safe_float(row[2]) for row in klines if len(row) > 2]
    lows = [value for value in lows if value > 0]
    highs = [value for value in highs if value > 0]
    if not lows or not highs:
        return None

    if direction == "long":
        stop_loss = _select_stop(
            current_price=current_price,
            structural_stop=min(lows),
            fallback_stop=current_price * (1 - _FALLBACK_STOP_PCT),
            direction=direction,
        )
        risk = current_price - stop_loss
        if risk <= 0:
            return None
        take_profit_1 = current_price + (risk * 2)
        take_profit_2 = current_price + (risk * 3)
    else:
        stop_loss = _select_stop(
            current_price=current_price,
            structural_stop=max(highs),
            fallback_stop=current_price * (1 + _FALLBACK_STOP_PCT),
            direction=direction,
        )
        risk = stop_loss - current_price
        if risk <= 0:
            return None
        take_profit_1 = current_price - (risk * 2)
        take_profit_2 = current_price - (risk * 3)
        if take_profit_1 <= 0 or take_profit_2 <= 0:
            return None

    return {
        "entry_type": "market",
        "entry_price": current_price,
        "entry_low": current_price * (1 - _ENTRY_ZONE_PCT),
        "entry_high": current_price * (1 + _ENTRY_ZONE_PCT),
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "risk_reward": 2.0,
    }


def _select_stop(
    *,
    current_price: float,
    structural_stop: float,
    fallback_stop: float,
    direction: str,
) -> float:
    """Prefer recent swing stops, falling back when distance is not usable."""
    if direction == "long":
        risk_pct = (current_price - structural_stop) / current_price
        if 0 < risk_pct <= _MAX_STOP_PCT:
            return structural_stop
    else:
        risk_pct = (structural_stop - current_price) / current_price
        if 0 < risk_pct <= _MAX_STOP_PCT:
            return structural_stop
    return fallback_stop


def _safe_float(value: object) -> float:
    """Convert numeric API values to float."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
