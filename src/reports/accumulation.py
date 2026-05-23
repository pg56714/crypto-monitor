"""Accumulation report formatter."""

from typing import Any

from src.reports.formatter import format_usd
from src.scoring.entry_engine import EntryPlan


def format_accumulation_pool(results: list[dict[str, Any]]) -> str:
    """Format accumulation pool scan results."""
    if not results:
        return "收籌雷達：目前沒有符合條件的標的。"

    lines = ["收籌雷達：標的池更新"]
    lines.extend(
        (
            f"{item['coin']} | score {item['score']:.0f} | "
            f"sideways {item['sideways_days']}d | avg vol {format_usd(item['avg_vol'])}"
        )
        for item in results[:20]
    )
    return "\n".join(lines)


def format_accumulation_scan(
    *,
    chase: list[dict[str, Any]],
    combined: list[dict[str, Any]],
    ambush: list[dict[str, Any]],
) -> str | None:
    """Format the hourly accumulation scan into three leaderboards."""
    if not chase and not combined and not ambush:
        return None
    lines = ["收籌雷達：三策略掃描"]
    if chase:
        lines.append("\n[追多] 費率排名")
        lines.extend(
            f"  {item['coin']} | 漲 {item['px_chg']:+.1f}% | 費率 {item['fr_pct']:+.3f}%"
            for item in sorted(chase, key=lambda r: float(r["fr_pct"]))[:10]
        )
    if combined:
        lines.append("\n[綜合] 四維均衡")
        lines.extend(
            f"  {item['coin']} | {item['total']:.0f} 分 | OI {item['d6h']:+.1f}%"
            for item in sorted(combined, key=lambda r: -float(r["total"]))[:10]
        )
    if ambush:
        lines.append("\n[埋伏] 中長線布局")
        for item in sorted(ambush, key=lambda r: -float(r["total"]))[:10]:
            lines.append(f"  {item['coin']} | {item['total']:.0f} 分 | 橫盤 {item['sw_days']}d")
            plan = item.get("entry_plan")
            if isinstance(plan, EntryPlan) and plan.is_valid:
                lines.append(_format_entry_plan(plan))
    return "\n".join(lines)


def _format_entry_plan(plan: EntryPlan) -> str:
    """Render an entry plan as a single indented Discord line."""
    return (
        f"    進場 {_fmt_price(plan.entry_low)}–{_fmt_price(plan.entry_high)}"
        f" | 停損 {_fmt_price(plan.stop_loss)}"
        f" | 目標 {_fmt_price(plan.take_profit_1)}/{_fmt_price(plan.take_profit_2)}"
        f" | 風報比 {plan.risk_reward:.1f}"
    )


def _fmt_price(value: float) -> str:
    """Format a price level with magnitude-appropriate precision."""
    if value <= 0:
        return "0"
    if value >= 1:
        return f"{value:,.2f}"
    return f"{value:.6f}".rstrip("0").rstrip(".")
