"""Quantstats backtest entry point for FiveFactor and Accumulation strategies."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from src.backtest.accumulation import run_accumulation_backtest
from src.backtest.data import fetch_server_time_ms, fetch_top_symbols, load_all
from src.backtest.five_factor import run_five_factor_backtest
from src.backtest.report import generate_report, print_summary
from src.core.config_reader import Config
from src.core.paths import get_notification_config_path

_STEP_MS = 3_600_000
_DAY_MS = 86_400_000
_ACC_POOL_LOOKBACK_DAYS = 240


async def _run(
    *,
    days: int,
    symbols: list[str] | None,
    top_n: int,
    strategy: str,
    output_dir: str,
    ff_timeframe: str | None,
    ff_session_tz: str,
    ff_session_start_hour: int | None,
    ff_session_end_hour: int | None,
) -> None:
    config = Config(get_notification_config_path())
    five_factor_config = _strategy_config(config, "FiveFactor")
    signal_timeframe = ff_timeframe or str(five_factor_config.get("timeframe", "5m"))
    data_timeframe = signal_timeframe if strategy in ("ff", "both") else "1h"
    dedup_hours = int(five_factor_config.get("dedup_hours", 4))

    server_time_ms = await fetch_server_time_ms()
    local_time_ms = int(datetime.now(UTC).timestamp() * 1000)
    base_time_ms = server_time_ms if server_time_ms > 0 else local_time_ms
    end_ms = (base_time_ms // _STEP_MS) * _STEP_MS
    start_ms = end_ms - days * 24 * _STEP_MS
    daily_start_ms = end_ms - _ACC_POOL_LOOKBACK_DAYS * _DAY_MS

    if not symbols:
        print(f"抓取前 {top_n} 大交易量幣種...")
        symbols = await fetch_top_symbols(top_n)
        print(f"幣種：{', '.join(symbols)}\n")

    print(f"下載歷史資料（{days} 天，{len(symbols)} 個幣種，signal={data_timeframe}）...")
    all_data = await load_all(
        symbols,
        start_ms=start_ms,
        end_ms=end_ms,
        daily_start_ms=daily_start_ms,
        signal_timeframe=data_timeframe,
        include_five_factor=strategy in ("ff", "both"),
        include_accumulation=strategy in ("acc", "both"),
    )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    ff_trades = []
    acc_trades = []

    for symbol, data in all_data.items():
        print(f"  回測 {symbol}...", end="", flush=True)
        if strategy in ("ff", "both"):
            new_ff = run_five_factor_backtest(
                data,
                start_ms=start_ms,
                end_ms=end_ms,
                dedup_hours=dedup_hours,
                session_timezone=ff_session_tz,
                session_start_hour=ff_session_start_hour,
                session_end_hour=ff_session_end_hour,
            )
            ff_trades.extend(new_ff)
            print(f" FF={len(new_ff)}", end="", flush=True)
        if strategy in ("acc", "both"):
            new_acc = run_accumulation_backtest(data, start_ms=start_ms, end_ms=end_ms)
            acc_trades.extend(new_acc)
            print(f" ACC={len(new_acc)}", end="", flush=True)
        print()

    if strategy in ("ff", "both"):
        print_summary(ff_trades, strategy_name="FiveFactor", start_ms=start_ms, end_ms=end_ms)
        generate_report(
            ff_trades,
            output_path=str(output / "five_factor.html"),
            title=(
                f"FiveFactor Backtest — {days}d / {len(all_data)} symbols / "
                f"{signal_timeframe} / "
                f"{_session_label(ff_session_tz, ff_session_start_hour, ff_session_end_hour)}"
            ),
            strategy_name="FiveFactor",
            start_ms=start_ms,
            end_ms=end_ms,
        )

    if strategy in ("acc", "both"):
        print_summary(acc_trades, strategy_name="Accumulation", start_ms=start_ms, end_ms=end_ms)
        generate_report(
            acc_trades,
            output_path=str(output / "accumulation.html"),
            title=f"Accumulation Backtest — {days}d / {len(all_data)} symbols",
            strategy_name="Accumulation",
            start_ms=start_ms,
            end_ms=end_ms,
        )

    if not ff_trades and not acc_trades:
        print("\n沒有產生任何交易紀錄。")


def _strategy_config(config: dict[str, Any], name: str) -> dict[str, Any]:
    value = config.get(name, {})
    return value if isinstance(value, dict) else {}


def _session_label(timezone: str, start_hour: int | None, end_hour: int | None) -> str:
    if start_hour is None or end_hour is None:
        return "all sessions"
    return f"{timezone} {start_hour:02d}:00-{end_hour:02d}:00"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="量化回測（FiveFactor + Accumulation）")
    parser.add_argument("--days", type=int, default=30, help="回測天數（預設 30）")
    parser.add_argument("--symbols", nargs="+", help="指定幣種（不指定則取前 N 大）")
    parser.add_argument("--top-n", type=int, default=20, help="取前 N 大交易量幣種（預設 20）")
    parser.add_argument(
        "--strategy",
        choices=["ff", "acc", "both"],
        default="both",
        help="ff=FiveFactor, acc=Accumulation, both=兩者（預設 both）",
    )
    parser.add_argument(
        "--output", default="backtest_output", help="輸出資料夾（預設 backtest_output）"
    )
    parser.add_argument(
        "--ff-timeframe",
        help="覆蓋 FiveFactor 回測 K 棒週期，例如 30m 或 1h；不填則讀取設定檔",
    )
    parser.add_argument(
        "--ff-session-tz",
        default="UTC",
        help="FiveFactor 進場時段判斷時區（預設 UTC，例如 Asia/Taipei）",
    )
    parser.add_argument(
        "--ff-session-start-hour",
        type=int,
        choices=range(24),
        metavar="0-23",
        help="FiveFactor 只允許此本地小時後進場（含）",
    )
    parser.add_argument(
        "--ff-session-end-hour",
        type=int,
        choices=range(24),
        metavar="0-23",
        help="FiveFactor 只允許此本地小時前進場（不含）",
    )
    args = parser.parse_args()
    if (args.ff_session_start_hour is None) != (args.ff_session_end_hour is None):
        parser.error("--ff-session-start-hour 和 --ff-session-end-hour 必須同時提供")
    return args


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        _run(
            days=args.days,
            symbols=args.symbols,
            top_n=args.top_n,
            strategy=args.strategy,
            output_dir=args.output,
            ff_timeframe=args.ff_timeframe,
            ff_session_tz=args.ff_session_tz,
            ff_session_start_hour=args.ff_session_start_hour,
            ff_session_end_hour=args.ff_session_end_hour,
        )
    )
