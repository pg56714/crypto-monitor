"""Long-short-ratio helpers."""


def long_short_ratio_direction(
    account_ratio: float,
    position_ratio: float,
    *,
    high_threshold: float = 2.0,
    low_threshold: float = 0.5,
) -> tuple[int, str]:
    """Detect whale divergence from account and position ratios."""
    if account_ratio < 1 and position_ratio > high_threshold:
        return 2, "counter_whale"
    if account_ratio > high_threshold and position_ratio < 1:
        return -2, "cautious_whale"
    if account_ratio > high_threshold and position_ratio > high_threshold:
        return 1, "consensus_bull"
    if account_ratio < low_threshold and position_ratio < low_threshold:
        return -1, "consensus_bear"
    return 0, "mixed"
