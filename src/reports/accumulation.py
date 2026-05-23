"""Accumulation report formatter."""

from typing import Any

from src.reports.formatter import format_price, format_usd
from src.scoring.entry_engine import EntryPlan


def format_accumulation_pool(results: list[dict[str, Any]]) -> str:
    """Format accumulation pool scan results."""
    if not results:
        return "目前沒有符合收籌條件的標的。"

    return "\n".join(
        (
            f"{item['coin']} | 分數 {item['score']:.0f} | "
            f"盤整 {item['sideways_days']} 天 | 均量 {format_usd(item['avg_vol'])}"
        )
        for item in results[:20]
    )


def format_accumulation_scan(
    *,
    chase: list[dict[str, Any]],
    combined: list[dict[str, Any]],
    ambush: list[dict[str, Any]],
) -> str | None:
    """Format the hourly accumulation scan into three leaderboards."""
    if not chase and not combined and not ambush:
        return None
    lines: list[str] = []
    if chase:
        lines.append("追價")
        lines.extend(
            f"  {item['coin']} | 漲跌 {item['px_chg']:+.1f}% | 資金費率 {item['fr_pct']:+.3f}%"
            for item in sorted(chase, key=lambda row: float(row["fr_pct"]))[:10]
        )
    if combined:
        if lines:
            lines.append("")
        lines.append("共振")
        lines.extend(
            f"  {item['coin']} | 分數 {item['total']:.0f} | OI {item['d6h']:+.1f}%"
            for item in sorted(combined, key=lambda row: -float(row["total"]))[:10]
        )
    if ambush:
        if lines:
            lines.append("")
        lines.append("埋伏")
        for item in sorted(ambush, key=lambda row: -float(row["total"]))[:10]:
            lines.append(f"  {item['coin']} | 分數 {item['total']:.0f} | 盤整 {item['sw_days']} 天")
            plan = item.get("entry_plan")
            if isinstance(plan, EntryPlan) and plan.is_valid:
                lines.append(_format_entry_plan(plan))
    return "\n".join(lines)


def _format_entry_plan(plan: EntryPlan) -> str:
    """Render an entry plan as a single indented Discord line."""
    return (
        f"    進場區 {format_price(plan.entry_low)} ~ {format_price(plan.entry_high)}"
        f" | 停損 {format_price(plan.stop_loss)}"
        f" | 目標 {format_price(plan.take_profit_1)} / {format_price(plan.take_profit_2)}"
        f" | 風報比 {plan.risk_reward:.1f}"
    )
