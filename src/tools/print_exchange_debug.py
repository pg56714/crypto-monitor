"""Execute and print the outputs of `self.exchange.*` calls for debugging."""

import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import ccxt.async_support as ccxt
import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.paths import get_notification_config_path
from src.core.config_reader import Config
from src.notifier.oi import OI as OINotifier

MAX_SYMBOLS_TO_PRINT = 5
OI_SUPPORTED_TIMEFRAMES = {
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
}


def _json_print(label: str, payload: object) -> None:
    """Pretty-print data as JSON with ASCII-only characters."""
    dumped = json.dumps(payload, indent=2, ensure_ascii=True, default=str)
    print(f"{label}:\n{dumped}")


async def _resolve_symbols(exchange: ccxt.binanceusdm, symbols_cfg: object) -> list[str]:
    """Resolve configured symbols, expanding `ALL` if requested."""
    if not symbols_cfg:
        return []

    if isinstance(symbols_cfg, str):
        if symbols_cfg.upper() == "ALL":
            return await _fetch_all_symbols(exchange)
        return [symbols_cfg]

    if isinstance(symbols_cfg, Sequence):
        cleaned = [symbol for symbol in symbols_cfg if isinstance(symbol, str) and symbol.strip()]
        if any(symbol.upper() == "ALL" for symbol in cleaned):
            return await _fetch_all_symbols(exchange)
        return cleaned

    return []


async def _fetch_all_symbols(exchange: ccxt.binanceusdm) -> list[str]:
    """Fetch and filter all linear USDT perpetual symbols."""
    await exchange.load_markets()
    symbols = [
        market["id"]
        for market in exchange.markets.values()
        if market.get("swap")
        and market.get("linear")
        and market.get("active")
        and market.get("quote") == "USDT"
    ]
    return sorted(symbols)


async def inspect_oi_calls() -> None:
    """Print the results of the exchange calls used by the OI notifier."""
    print("=== Inspecting OI notifier exchange calls ===")
    notifier = OINotifier()
    try:
        oi_df = await notifier.getOI()
    finally:
        await notifier.exchange.close()

    threshold = notifier.threshold_pct
    timeframe = notifier.config.get("timeframe", "5m")
    if timeframe not in OI_SUPPORTED_TIMEFRAMES:
        timeframe = "5m"

    print(f"Threshold: {threshold:.4f}%")

    if oi_df.is_empty():
        print("No OI data fetched.")
        return

    filtered = oi_df.filter(pl.col("oi_pct").abs() >= threshold)
    filtered = filtered.sort(pl.col("oi_pct").abs(), descending=True, nulls_last=True)

    if filtered.is_empty():
        print("No symbols exceed the configured threshold.")
        preview = oi_df.sort(pl.col("oi_pct").abs(), descending=True, nulls_last=True).head(
            MAX_SYMBOLS_TO_PRINT
        )
        if not preview.is_empty():
            _print_oi_summary(preview, heading="Top OI movers (reference)")
        return

    total_hits = filtered.height
    display_df = filtered.head(MAX_SYMBOLS_TO_PRINT)
    if total_hits > MAX_SYMBOLS_TO_PRINT:
        print(
            f"Showing first {MAX_SYMBOLS_TO_PRINT} symbols out of "
            f"{total_hits} exceeding the threshold."
        )
    else:
        print(f"{total_hits} symbols exceed the threshold.")

    _print_oi_summary(display_df)
    await _print_oi_history([row["symbol"] for row in display_df.iter_rows(named=True)], timeframe)


async def inspect_volume_calls() -> None:
    """Print the results of the exchange calls used by the VolumeBomb notifier."""
    print("\n=== Inspecting VolumeBomb notifier exchange calls ===")
    config = Config(get_notification_config_path())["VolumeBomb"]
    timeframe = config.get("timeframe", "5m")

    exchange = ccxt.binanceusdm()
    try:
        symbols = await _resolve_symbols(exchange, config.get("valid_symbol"))
        if not symbols:
            print("No symbols configured for VolumeBomb notifier.")
            return

        symbols_to_check = symbols[:MAX_SYMBOLS_TO_PRINT]
        if len(symbols) > MAX_SYMBOLS_TO_PRINT:
            print(f"Showing first {MAX_SYMBOLS_TO_PRINT} symbols out of {len(symbols)} total.")

        for symbol in symbols_to_check:
            print(f"\n--- {symbol} ---")
            try:
                ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=5)
                _json_print("fetch_ohlcv", ohlcv)
            except Exception as exc:  # noqa: BLE001
                print(f"fetch_ohlcv error: {exc}")
    finally:
        await exchange.close()


def _print_oi_summary(df: pl.DataFrame, heading: str | None = None) -> None:
    """Pretty-print a compact summary of OI changes."""
    if df.is_empty():
        return

    if heading:
        print(f"\n{heading}")

    for row in df.iter_rows(named=True):
        symbol = row["symbol"]
        oi_val = row.get("oi")
        oi_pct = row.get("oi_pct")
        price = row.get("price")
        funding_pct = row.get("funding_pct")

        oi_str = "N/A" if oi_val is None else f"{oi_val:,.0f}"
        oi_pct_str = "N/A" if oi_pct is None else f"{oi_pct:+.3f}%"
        price_str = "N/A" if price is None else f"{price:.4f}"
        funding_str = "N/A" if funding_pct is None else f"{funding_pct:+.4f}%"

        print(
            f"- {symbol}: oi={oi_str}, oi_pct={oi_pct_str}, "
            f"price={price_str}, funding={funding_str}"
        )


async def _print_oi_history(symbols: list[str], timeframe: str) -> None:
    """Fetch and display raw open interest history for selected symbols."""
    if not symbols:
        return

    print("\nRaw open interest history for inspected symbols:")
    exchange = ccxt.binanceusdm()
    try:
        for symbol in symbols:
            try:
                history = await exchange.fetch_open_interest_history(
                    symbol,
                    timeframe=timeframe,
                    limit=3,
                )
                _json_print(f"{symbol} fetch_open_interest_history", history)
            except Exception as exc:  # noqa: BLE001
                print(f"{symbol} fetch_open_interest_history error: {exc}")
    finally:
        await exchange.close()


async def main() -> None:
    """Execute and print the outputs of `self.exchange.*` calls for debugging."""
    await inspect_oi_calls()
    await inspect_volume_calls()


if __name__ == "__main__":
    asyncio.run(main())
