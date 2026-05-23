"""Five-factor futures signal scoring."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FiveFactorScore:
    """Five-factor score result."""

    score: int
    verdict: str


def score_five_factor(
    *,
    funding_dir: int,
    cvd_dir: int,
    oi_dir: int,
    lsr_dir: int,
    dprice_dir: int,
) -> FiveFactorScore:
    """Calculate the five-factor score and verdict."""
    score = funding_dir + cvd_dir + oi_dir + lsr_dir + dprice_dir
    if score >= 4:
        verdict = "Entry Long"
    elif score >= 2:
        verdict = "Watch Long"
    elif score <= -4:
        verdict = "Entry Short"
    elif score <= -2:
        verdict = "Watch Short"
    else:
        verdict = "Ignore"
    return FiveFactorScore(score=score, verdict=verdict)


def detect_patterns(
    *,
    funding_rate: float,
    oi_dir: int,
    cvd_dir: int,
    dprice_dir: int,
    lsr_global: float,
    lsr_account: float,
    lsr_position: float,
) -> list[str]:
    """Detect named futures signal patterns."""
    patterns: list[str] = []
    if funding_rate < 0 and cvd_dir > 0 and oi_dir > 0:
        patterns.append("short_squeeze")
    if funding_rate > 0 and cvd_dir < 0 and oi_dir < 0:
        patterns.append("long_capitulation")
    if dprice_dir > 0 and oi_dir > 0 and lsr_global > 1:
        patterns.append("healthy_up")
    elif dprice_dir > 0 and oi_dir < 0 and lsr_global > 1:
        patterns.append("exhaust_up")
    elif dprice_dir < 0 and oi_dir > 0 and lsr_global < 1:
        patterns.append("healthy_down")
    elif dprice_dir < 0 and oi_dir < 0 and lsr_global > 1:
        patterns.append("long_capitulate")
    if lsr_account < 1 and lsr_position > 2:
        patterns.append("counter_whale")
    if lsr_account > 2 and lsr_position < 1:
        patterns.append("cautious_whale")
    return patterns
