"""Quantstats report generation from a list of Trade objects."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

import pandas as pd
import quantstats as qs

if TYPE_CHECKING:
    from src.backtest.trade import Trade


def generate_report(
    trades: list[Trade],
    *,
    output_path: str,
    title: str,
    strategy_name: str = "Strategy",
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> None:
    """Generate a quantstats HTML tearsheet for a list of completed trades."""
    returns = _trades_to_returns(trades, start_ms=start_ms, end_ms=end_ms)
    if returns.empty:
        print(f"  ({strategy_name} 無交易可產生報表)")
        _write_empty_report(output_path=output_path, title=title, strategy_name=strategy_name)
        return
    qs.reports.html(returns, output=output_path, title=title, benchmark=None)
    print(f"  → {output_path}")


def print_summary(
    trades: list[Trade],
    *,
    strategy_name: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> None:
    """Print a brief text summary of trade results to stdout."""
    completed = [t for t in trades if t.pnl_pct is not None]
    if not completed:
        print(f"\n[{strategy_name}] 無已結束的交易。")
        return

    wins = [t for t in completed if (t.pnl_pct or 0) > 0]
    total_pnl = sum(t.pnl_pct or 0 for t in completed)
    compounded_pnl = 1.0
    for trade in completed:
        compounded_pnl *= 1 + (trade.pnl_pct or 0)
    compounded_pnl -= 1
    win_rate = len(wins) / len(completed) * 100
    avg_pnl = total_pnl / len(completed) * 100

    exit_counts: dict[str, int] = {}
    for t in completed:
        key = t.exit_reason or "unknown"
        exit_counts[key] = exit_counts.get(key, 0) + 1

    print(f"\n[{strategy_name}]")
    print(f"  總交易數：{len(completed)}")
    print(f"  勝率：{win_rate:.1f}%")
    print(f"  平均報酬：{avg_pnl:+.2f}%")
    print(f"  複合報酬：{compounded_pnl * 100:.2f}%")
    exit_str = "  ".join(f"{k}={v}" for k, v in sorted(exit_counts.items()))
    print(f"  出場分布：{exit_str}")

    if len(completed) >= 3:
        returns = _trades_to_returns(trades, start_ms=start_ms, end_ms=end_ms)
        if not returns.empty:
            sharpe = qs.stats.sharpe(returns)
            max_dd = qs.stats.max_drawdown(returns)
            print(f"  Sharpe：{sharpe:.2f}  最大回撤：{max_dd * 100:.2f}%")


def _trades_to_returns(
    trades: list[Trade],
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> pd.Series:  # type: ignore[type-arg]
    """Convert completed trades to a daily compounded return series for quantstats."""
    completed = sorted(
        [
            (t.exit_time_ms, t.pnl_pct)
            for t in trades
            if t.exit_time_ms is not None and t.pnl_pct is not None
        ],
        key=lambda item: item[0],
    )
    if not completed:
        return pd.Series(dtype=float)

    daily_growth: dict[object, float] = {}
    for exit_ms, pnl in completed:
        date = pd.to_datetime(exit_ms, unit="ms", utc=True).date()
        daily_growth[date] = daily_growth.get(date, 1.0) * (1 + pnl)

    start = _date_from_ms(start_ms) if start_ms is not None else min(daily_growth)
    end = _date_from_ms(end_ms) if end_ms is not None else max(daily_growth)
    if start > end:
        return pd.Series(dtype=float)
    index = pd.date_range(start=start, end=end, freq="D")
    values = [daily_growth.get(day.date(), 1.0) - 1 for day in index]
    return pd.Series(values, index=index, dtype=float)


def _date_from_ms(timestamp_ms: int) -> object:
    """Return the UTC calendar date for a millisecond timestamp."""
    return pd.to_datetime(timestamp_ms, unit="ms", utc=True).date()


def _write_empty_report(*, output_path: str, title: str, strategy_name: str) -> None:
    """Write an HTML report placeholder when no completed trades are available."""
    html = f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <title>{escape(title)}</title>
  <style>
    body {{
      font-family: Arial, "Microsoft JhengHei", sans-serif;
      margin: 40px;
      color: #1f2937;
      background: #f8fafc;
    }}
    main {{
      max-width: 760px;
      padding: 28px;
      border: 1px solid #d1d5db;
      border-radius: 8px;
      background: #ffffff;
    }}
    h1 {{ margin-top: 0; font-size: 24px; }}
    p {{ line-height: 1.7; }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(title)}</h1>
    <p>
      {escape(strategy_name)} 在本次回測區間內沒有已結束交易，
      因此沒有 QuantStats 績效圖表可產生。
    </p>
  </main>
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(html)
    print(f"  → {output_path}")
