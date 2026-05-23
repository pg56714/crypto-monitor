"""Cumulative volume delta helpers."""


def calculate_cvd_from_klines(klines: list[list[float | int]]) -> float:
    """Calculate CVD from Binance kline rows."""
    deltas: list[float] = []
    for row in klines:
        if len(row) <= 10:
            continue
        quote_volume = float(row[7])
        taker_buy_quote_volume = float(row[10])
        deltas.append((2 * taker_buy_quote_volume) - quote_volume)
    return sum(deltas)


def direction_from_value(value: float, *, threshold: float = 0.0) -> int:
    """Convert a signed value into -1, 0, or 1."""
    if value > threshold:
        return 1
    if value < -threshold:
        return -1
    return 0
