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
        verdict = "做多進場"
    elif score <= -4:
        verdict = "做空進場"
    else:
        verdict = "忽略"
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
        patterns.append("空頭擠壓")
    if funding_rate > 0 and cvd_dir < 0 and oi_dir < 0:
        patterns.append("多頭投降")
    if dprice_dir > 0 and oi_dir > 0 and lsr_global > 1:
        patterns.append("健康上漲")
    elif dprice_dir > 0 and oi_dir < 0 and lsr_global > 1:
        patterns.append("上漲衰竭")
    elif dprice_dir < 0 and oi_dir > 0 and lsr_global < 1:
        patterns.append("健康下跌")
    elif dprice_dir < 0 and oi_dir < 0 and lsr_global > 1:
        patterns.append("多頭投降")
    if lsr_account < 1 and lsr_position > 2:
        patterns.append("巨鯨逆勢偏多")
    if lsr_account > 2 and lsr_position < 1:
        patterns.append("巨鯨謹慎偏空")
    return list(dict.fromkeys(patterns))
