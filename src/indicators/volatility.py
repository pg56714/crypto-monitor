"""Volatility and range helpers."""


def range_pct(low: float, high: float) -> float:
    """Return high-low range as a percentage of low."""
    if low <= 0:
        return 0.0
    return ((high - low) / low) * 100
