"""Funding-rate signal helpers."""


def funding_direction(
    current_rate: float,
    previous_rate: float,
    *,
    hot_threshold: float = 0.0005,
) -> tuple[int, str]:
    """Classify funding-rate direction and overheating state."""
    if current_rate < 0 <= previous_rate:
        return 1, "just_turned_negative"
    if current_rate > 0 >= previous_rate:
        return -1, "just_turned_positive"
    if current_rate > hot_threshold:
        return -1, "overheated_long"
    if current_rate < -hot_threshold:
        return 1, "overheated_short"
    return 0, "neutral"
