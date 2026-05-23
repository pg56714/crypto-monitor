"""Five-factor report formatter."""

from typing import Any


def format_five_factor_alert(signals: list[dict[str, Any]]) -> str | None:
    """Format five-factor alerts for Discord."""
    if not signals:
        return None
    lines = ["[五件套訊號]"]
    for signal in sorted(signals, key=lambda item: -abs(int(item["score"]))):
        lines.extend(
            [
                "```",
                f"{signal['symbol']} score {signal['score']:+d} -> {signal['verdict']}",
                f"patterns: {', '.join(signal.get('patterns', []))}",
                f"funding: {signal.get('funding_rate', 0):+.4%}",
                f"OI change: {signal.get('oi_change_pct', 0):+.2f}%",
                f"CVD: {signal.get('cvd', 0):+.2f}",
                f"LSR: {signal.get('lsr_global', 0):.2f}",
                "```",
            ]
        )
    return "\n".join(lines)
