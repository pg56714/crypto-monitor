"""Shared report formatting helpers."""


def format_usd(value: float) -> str:
    """Format a USD value with compact units."""
    if value >= 1e9:
        return f"${value / 1e9:.1f}B"
    if value >= 1e6:
        return f"${value / 1e6:.1f}M"
    if value >= 1e3:
        return f"${value / 1e3:.0f}K"
    return f"${value:.0f}"


def format_price(value: float) -> str:
    """Format a price level with magnitude-appropriate precision."""
    if value <= 0:
        return "0"
    if value >= 1:
        return f"{value:,.2f}"
    return f"{value:.8f}".rstrip("0").rstrip(".")
