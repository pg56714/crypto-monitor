"""Accumulation report formatter."""

import unicodedata
from typing import Any

from src.reports.formatter import format_price, format_usd
from src.scoring.entry_engine import EntryPlan

_POOL_LIMIT = 20
_SCAN_LIMIT = 10


def format_accumulation_pool(results: list[dict[str, Any]]) -> str:
    """Format accumulation pool scan results."""
    if not results:
        return "目前沒有符合收籌條件的標的。"

    rows: list[tuple[str, ...]] = []
    for item in results[:_POOL_LIMIT]:
        try:
            rows.append(
                (
                    str(item["coin"]),
                    f"{float(item['score']):.0f}",
                    f"{float(item['sideways_days']):.0f} 天",
                    format_usd(float(item["avg_vol"])),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    if not rows:
        return "目前沒有符合收籌條件的標的。"
    return _format_table(f"收籌候選 Top {_POOL_LIMIT}", ("代幣", "分數", "盤整", "均量"), rows)


def format_accumulation_scan(
    *,
    ambush: list[dict[str, Any]],
) -> str | None:
    """Format the hourly accumulation scan into ambush candidates."""
    if not ambush:
        return None
    sorted_rows = _sorted_scan_rows(ambush)
    if not sorted_rows:
        return None
    lines = [f"埋伏候選 Top {len(sorted_rows)}", "```text"]
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
    """Return the highest-scored scan rows, skipping malformed items."""
    valid = []
    for item in ambush:
        try:
            float(item["total"])
            float(item["sw_days"])
            item["coin"]
        except (KeyError, TypeError, ValueError):
            continue
        valid.append(item)
    return sorted(valid, key=lambda item: -float(item["total"]))[:_SCAN_LIMIT]


def _format_entry_plan(plan: EntryPlan) -> str:
    """Render entry plan as two compact indented lines that fit Discord mobile width."""
    line1 = f"  Limit {format_price(plan.limit_price)}  Valid {plan.entry_wait_hours}h"
    line2 = f"  SL {format_price(plan.stop_loss)}"
    line3 = (
        f"  TP {format_price(plan.take_profit_1)}/{format_price(plan.take_profit_2)}"
        f"  RR {plan.risk_reward:.1f}"
    )
    return f"{line1}\n{line2}\n{line3}"


def _format_table(title: str, headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    """Render rows as a Discord-friendly fixed-width table."""
    n = len(headers)
    valid_rows = [row for row in rows if len(row) == n]
    widths = _column_widths(headers, valid_rows)
    lines = [
        title,
        "```text",
        _format_row(headers, widths),
        _format_row(tuple("-" * width for width in widths), widths),
    ]
    lines.extend(_format_row(row, widths) for row in valid_rows)
    lines.append("```")
    return "\n".join(lines)


def _dw(text: str) -> int:
    """Display width of text; CJK/full-width chars count as 2 columns."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def _column_widths(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[int]:
    """Calculate display-width-aware column widths for Discord monospace tables."""
    if not rows:
        return [_dw(h) for h in headers]
    return [
        max(_dw(headers[index]), *(_dw(row[index]) for row in rows))
        for index in range(len(headers))
    ]


def _format_row(row: tuple[str, ...], widths: list[int]) -> str:
    """Format one fixed-width row using display width for padding."""

    def _ljust(text: str, width: int) -> str:
        return text + " " * max(0, width - _dw(text))

    def _rjust(text: str, width: int) -> str:
        return " " * max(0, width - _dw(text)) + text

    formatted = [_ljust(row[0], widths[0])]
    formatted.extend(_rjust(value, width) for value, width in zip(row[1:], widths[1:], strict=True))
    return "  ".join(formatted)
