"""Open-interest trend helpers."""


def segment_averages(values: list[float], *, segment_count: int = 4) -> list[float]:
    """Split values into equal segments and return each segment average."""
    if len(values) < segment_count:
        return []

    segment_size = len(values) // segment_count
    if segment_size == 0:
        return []

    segments: list[float] = []
    for index in range(segment_count):
        start = index * segment_size
        end = start + segment_size if index < segment_count - 1 else len(values)
        segment = values[start:end]
        segments.append(sum(segment) / len(segment))
    return segments


def open_interest_direction(
    values: list[float],
    *,
    change_threshold_pct: float = 5.0,
) -> tuple[int, float, list[float]]:
    """Return OI direction, percentage change, and four segment averages."""
    segments = segment_averages(values)
    if len(segments) < 2 or segments[0] <= 0:
        return 0, 0.0, segments

    change_pct = ((segments[-1] - segments[0]) / segments[0]) * 100
    if change_pct > change_threshold_pct:
        return 1, change_pct, segments
    if change_pct < -change_threshold_pct:
        return -1, change_pct, segments
    return 0, change_pct, segments
