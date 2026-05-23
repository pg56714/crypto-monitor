"""Five-factor report formatter."""

from typing import Any

from src.reports.formatter import format_price


def format_five_factor_alert(signals: list[dict[str, Any]]) -> str | None:
    """Format five-factor alerts for Discord."""
    if not signals:
        return None

    lines: list[str] = []
    for signal in sorted(signals, key=lambda item: -abs(int(item["score"]))):
        block = [
            "```",
            f"{signal['symbol']} | {signal['verdict']} | 分數 {int(signal['score']):+d}",
            f"週期：{signal.get('timeframe', 'n/a')}",
            f"目前價格：{format_price(_get_float(signal, 'current_price'))}",
            f"資金費率：{_get_float(signal, 'funding_rate'):+.4%}",
            f"OI 變化：{_get_float(signal, 'oi_change_pct'):+.2f}%",
            f"CVD：{_get_float(signal, 'cvd'):+.2f}",
            f"多空比：{_get_float(signal, 'lsr_global'):.2f}",
        ]
        patterns = signal.get("patterns", [])
        if isinstance(patterns, list) and patterns:
            block.append(f"型態：{', '.join(str(pattern) for pattern in patterns)}")
        trade_plan = signal.get("trade_plan")
        if isinstance(trade_plan, dict):
            block.extend(_format_trade_plan(trade_plan))
        block.append("```")
        lines.extend(block)
    return "\n".join(lines)


def _format_trade_plan(trade_plan: dict[str, Any]) -> list[str]:
    """Format a market-entry trade plan."""
    entry_low = _get_float(trade_plan, "entry_low")
    entry_high = _get_float(trade_plan, "entry_high")
    stop_loss = _get_float(trade_plan, "stop_loss")
    take_profit_1 = _get_float(trade_plan, "take_profit_1")
    take_profit_2 = _get_float(trade_plan, "take_profit_2")
    risk_reward = _get_float(trade_plan, "risk_reward")
    if min(entry_low, entry_high, stop_loss, take_profit_1, take_profit_2) <= 0:
        return []
    return [
        f"進場區：{format_price(entry_low)} ~ {format_price(entry_high)}",
        f"停損：{format_price(stop_loss)}",
        f"目標：{format_price(take_profit_1)} / {format_price(take_profit_2)}",
        f"風報比：{risk_reward:.1f}",
    ]


def _get_float(data: dict[str, Any], key: str) -> float:
    """Read a float field from a report row."""
    value = data.get(key, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
