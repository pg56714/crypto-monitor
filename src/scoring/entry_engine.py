"""Shared entry-plan calculation."""

from dataclasses import dataclass

DEFAULT_ENTRY_WAIT_HOURS = 48
DEFAULT_MIN_RISK_REWARD = 2.0
DEFAULT_LIMIT_ENTRY_RATIO = 1.0
DEFAULT_MIN_ENTRY_PRICE_CHANGE_PCT = 0.0
DEFAULT_MAX_ENTRY_PRICE_CHANGE_PCT = 5.0
RISK_REWARD_EPSILON = 1e-9


@dataclass(frozen=True)
class EntryPlan:
    """Risk-reward entry plan."""

    entry_low: float
    entry_high: float
    limit_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_reward: float
    is_valid: bool
    entry_wait_hours: int = DEFAULT_ENTRY_WAIT_HOURS


def build_entry_plan(
    *,
    avg_whale_price: float,
    support: float,
    resistance: float,
    volume_spike: bool,
    whale_inflow: bool,
    min_risk_reward: float = DEFAULT_MIN_RISK_REWARD,
    entry_wait_hours: int = DEFAULT_ENTRY_WAIT_HOURS,
    limit_entry_ratio: float = DEFAULT_LIMIT_ENTRY_RATIO,
) -> EntryPlan | None:
    """Build a shared entry plan for strategy reports."""
    if avg_whale_price <= 0 or support <= 0 or resistance <= 0:
        return None
    if not volume_spike or not whale_inflow:
        return None

    entry_low = support
    stop_loss = support * 0.97
    take_profit_1 = resistance
    take_profit_2 = resistance * 1.2
    max_entry = _max_entry_for_risk_reward(
        stop_loss=stop_loss,
        take_profit=take_profit_1,
        min_risk_reward=min_risk_reward,
    )
    entry_high = min(avg_whale_price, max_entry)
    limit_ratio = min(max(limit_entry_ratio, 0.0), 1.0)
    limit_price = entry_low + ((entry_high - entry_low) * limit_ratio)
    risk_reward = calculate_risk_reward(limit_price, stop_loss, take_profit_1)
    is_valid = (
        entry_high >= entry_low
        and entry_low <= limit_price <= entry_high
        and risk_reward + RISK_REWARD_EPSILON >= min_risk_reward
    )
    return EntryPlan(
        entry_low=entry_low,
        entry_high=entry_high,
        limit_price=limit_price,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,
        risk_reward=risk_reward,
        is_valid=is_valid,
        entry_wait_hours=entry_wait_hours,
    )


def entry_momentum_is_valid(
    price_change_pct: float,
    *,
    min_price_change_pct: float = DEFAULT_MIN_ENTRY_PRICE_CHANGE_PCT,
    max_price_change_pct: float = DEFAULT_MAX_ENTRY_PRICE_CHANGE_PCT,
) -> bool:
    """Return True when an accumulation entry is rising but not extended."""
    return min_price_change_pct <= price_change_pct <= max_price_change_pct


def calculate_risk_reward(entry_price: float, stop_loss: float, take_profit: float) -> float:
    """Calculate long-side reward divided by risk for a planned entry."""
    risk = entry_price - stop_loss
    reward = take_profit - entry_price
    if risk <= 0:
        return 0.0
    return reward / risk


def _max_entry_for_risk_reward(
    *,
    stop_loss: float,
    take_profit: float,
    min_risk_reward: float,
) -> float:
    if min_risk_reward <= 0:
        return take_profit
    return (take_profit + min_risk_reward * stop_loss) / (min_risk_reward + 1)
