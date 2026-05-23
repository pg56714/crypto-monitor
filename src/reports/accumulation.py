"""Accumulation report formatter."""

from typing import Any

from src.reports.formatter import format_price, format_usd
from src.scoring.entry_engine import EntryPlan

_POOL_LIMIT = 20
_SCAN_LIMIT = 10


def format_accumulation_pool(results: list[dict[str, Any]]) -> str:
    """Format accumulation pool scan results."""
    if not results:
        return "目前沒有符合收籌條件的標的。"

    rows = [
        (
            str(item["coin"]),
            f"{float(item['score']):.0f}",
            f"{float(item['sideways_days']):.0f} 天",
            format_usd(float(item["avg_vol"])),
        )
        for item in results[:_POOL_LIMIT]
    ]
    return _format_table("收籌候選 Top 20", ("代幣", "分數", "盤整", "均量"), rows)


def format_accumulation_scan(
    *,
    ambush: list[dict[str, Any]],
) -> str | None:
    """Format the hourly accumulation scan into ambush candidates."""
    if not ambush:
        return None
    lines = ["埋伏候選 Top 10", "```text"]
    sorted_rows = _sorted_scan_rows(ambush)
    rows = [
        (
            str(item["coin"]),
            f"{float(item['total']):.0f}",
            f"{float(item['sw_days']):.0f} 天",
        )
        for item in sorted_rows
    ]
    widths = _column_widths(("代幣", "分數", "盤整"), rows)
    lines.append(_format_row(("代幣", "分數", "盤整"), widths))
    lines.append(_format_row(("-" * widths[0], "-" * widths[1], "-" * widths[2]), widths))
    for item, row in zip(sorted_rows, rows, strict=True):
        lines.append(_format_row(row, widths))
        plan = item.get("entry_plan")
        if isinstance(plan, EntryPlan) and plan.is_valid:
            lines.append(_format_entry_plan(plan))
    lines.append("```")
    return "\n".join(lines)


def _sorted_scan_rows(ambush: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the highest-scored scan rows."""
    return sorted(ambush, key=lambda item: -float(item["total"]))[:_SCAN_LIMIT]


def _format_entry_plan(plan: EntryPlan) -> str:
    """Render an entry plan as a single indented Discord line."""
    return (
        f"    進場區 {format_price(plan.entry_low)} ~ {format_price(plan.entry_high)}"
        f" | 停損 {format_price(plan.stop_loss)}"
        f" | 目標 {format_price(plan.take_profit_1)} / {format_price(plan.take_profit_2)}"
        f" | 風報比 {plan.risk_reward:.1f}"
    )


def _format_table(title: str, headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    """Render rows as a Discord-friendly fixed-width table."""
    widths = _column_widths(headers, rows)
    lines = [
        title,
        "```text",
        _format_row(headers, widths),
        _format_row(tuple("-" * width for width in widths), widths),
    ]
    lines.extend(_format_row(row, widths) for row in rows)
    lines.append("```")
    return "\n".join(lines)


def _column_widths(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[int]:
    """Calculate simple fixed-width columns for ASCII-heavy Discord rows."""
    return [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]


def _format_row(row: tuple[str, ...], widths: list[int]) -> str:
    """Format one fixed-width row."""
    formatted = [row[0].ljust(widths[0])]
    formatted.extend(value.rjust(width) for value, width in zip(row[1:], widths[1:], strict=True))
    return "  ".join(formatted)
