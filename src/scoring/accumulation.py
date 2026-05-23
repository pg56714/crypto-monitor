"""Accumulation-radar scoring rules."""

from collections.abc import Mapping
from typing import Any


def score_chase_signal(data: Mapping[str, Any]) -> dict[str, Any] | None:
    """Score a chase-long candidate from normalized market data."""
    if data["px_chg"] <= 3 or data["fr_pct"] >= -0.005 or data["vol"] <= 1_000_000:
        return None
    return {**dict(data), "score_type": "chase"}


def score_combined_signal(data: Mapping[str, Any]) -> dict[str, Any] | None:
    """Score the balanced accumulation model."""
    f_sc = _score_negative_funding(float(data["fr_pct"]), max_score=25)
    m_sc = _score_market_cap(float(data["est_mcap"]), [50e6, 100e6, 200e6, 300e6, 500e6, 1e9])
    s_sc = _score_sideways_days(int(data["sw_days"]), [120, 90, 75, 60, 45], [25, 22, 18, 14, 10])
    o_sc = _score_abs_value(abs(float(data["d6h"])), [15, 8, 5, 3, 2], [25, 22, 18, 14, 10])
    total = f_sc + m_sc + s_sc + o_sc
    if total < 25:
        return None
    return {**dict(data), "total": total, "f_sc": f_sc, "m_sc": m_sc, "s_sc": s_sc, "o_sc": o_sc}


def score_ambush_signal(data: Mapping[str, Any]) -> dict[str, Any] | None:
    """Score the longer-horizon ambush model."""
    if not data["in_pool"] or data["px_chg"] > 50:
        return None

    m_sc = _score_market_cap(
        float(data["est_mcap"]),
        [50e6, 100e6, 150e6, 200e6, 300e6, 500e6, 1e9],
        [35, 32, 28, 25, 20, 12, 5],
    )
    o_sc = _score_abs_value(abs(float(data["d6h"])), [10, 5, 3, 2, 1], [30, 25, 20, 14, 8])
    if data["d6h"] > 2 and abs(float(data["px_chg"])) < 5:
        o_sc = min(o_sc + 5, 30)
    s_sc = _score_sideways_days(int(data["sw_days"]), [120, 90, 75, 60, 45], [20, 17, 14, 10, 6])
    f_sc = _score_negative_funding(float(data["fr_pct"]), max_score=15)
    total = m_sc + o_sc + s_sc + f_sc
    if total < 20:
        return None
    return {**dict(data), "total": total, "m_sc": m_sc, "o_sc": o_sc, "s_sc": s_sc, "f_sc": f_sc}


def _score_market_cap(
    market_cap: float,
    thresholds: list[float],
    scores: list[int] | None = None,
) -> int:
    scores = scores or [25, 22, 20, 17, 12, 7]
    if market_cap <= 0:
        return 0
    for threshold, score in zip(thresholds, scores, strict=False):
        if market_cap < threshold:
            return score
    return 0


def _score_sideways_days(days: int, thresholds: list[int], scores: list[int]) -> int:
    for threshold, score in zip(thresholds, scores, strict=True):
        if days >= threshold:
            return score
    return 0


def _score_abs_value(value: float, thresholds: list[float], scores: list[int]) -> int:
    for threshold, score in zip(thresholds, scores, strict=True):
        if value >= threshold:
            return score
    return 0


def _score_negative_funding(funding_pct: float, *, max_score: int) -> int:
    if max_score == 15:
        if funding_pct < -0.1:
            return 15
        if funding_pct < -0.05:
            return 12
        if funding_pct < -0.03:
            return 9
        if funding_pct < -0.01:
            return 6
        if funding_pct < 0:
            return 3
        return 0

    if funding_pct < -0.5:
        return 25
    if funding_pct < -0.1:
        return 22
    if funding_pct < -0.05:
        return 18
    if funding_pct < -0.03:
        return 14
    if funding_pct < -0.01:
        return 10
    if funding_pct < 0:
        return 5
    return 0
