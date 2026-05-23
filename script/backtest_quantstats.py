"""Quantstats backtest entry point for FiveFactor and Accumulation strategies."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from src.backtest.accumulation import run_accumulation_backtest
from src.backtest.data import fetch_top_symbols, load_all
from src.backtest.five_factor import run_five_factor_backtest
from src.backtest.report import generate_report, print_summary

_STEP_MS = 3_600_000
_DAY_MS = 86_400_000


async def _run(
    *,
    days: int,
    symbols: list[str] | None,
    top_n: int,
    strategy: str,
    output_dir: str,
) -> None:
    now = datetime.now(UTC)
    end_ms = (int(now.timestamp() * 1000) // _STEP_MS) * _STEP_MS
    start_ms = end_ms - days * 24 * _STEP_MS
    daily_start_ms = end_ms - 240 * _DAY_MS

    if not symbols:
        print(f"抓取前 {top_n} 大交易量幣種...")
        symbols = await fetch_top_symbols(top_n)
        print(f"幣種：{', '.join(symbols)}\n")

    print(f"下載歷史資料（{days} 天，{len(symbols)} 個幣種）...")
    all_data = await load_all(
        symbols, start_ms=start_ms, end_ms=end_ms, daily_start_ms=daily_start_ms
    )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    ff_trades = []
    acc_trades = []

    for symbol, data in all_data.items():
        print(f"  回測 {symbol}...", end="", flush=True)
        if strategy in ("ff", "both"):
            new_ff = run_five_factor_backtest(data, start_ms=start_ms, end_ms=end_ms)
            ff_trades.extend(new_ff)
            print(f" FF={len(new_ff)}", end="", flush=True)
        if strategy in ("acc", "both"):
            new_acc = run_accumulation_backtest(data, start_ms=start_ms, end_ms=end_ms)
            acc_trades.extend(new_acc)
            print(f" ACC={len(new_acc)}", end="", flush=True)
        print()

    if strategy in ("ff", "both"):
        print_summary(ff_trades, strategy_name="FiveFactor")
        generate_report(
            ff_trades,
            output_path=str(output / "five_factor.html"),
            title=f"FiveFactor Backtest — {days}d / {len(all_data)} symbols",
            strategy_name="FiveFactor",
        )

    if strategy in ("acc", "both"):
        print_summary(acc_trades, strategy_name="Accumulation")
        generate_report(
            acc_trades,
            output_path=str(output / "accumulation.html"),
            title=f"Accumulation Backtest — {days}d / {len(all_data)} symbols",
            strategy_name="Accumulation",
        )

    if not ff_trades and not acc_trades:
        print("\n沒有產生任何交易紀錄。")


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
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        _run(
            days=args.days,
            symbols=args.symbols,
            top_n=args.top_n,
            strategy=args.strategy,
            output_dir=args.output,
        )
    )
