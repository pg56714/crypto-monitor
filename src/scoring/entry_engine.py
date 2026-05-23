"""Shared entry-plan calculation."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EntryPlan:
    """Risk-reward entry plan."""

    entry_low: float
    entry_high: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_reward: float
    breakout_entry: float | None
    is_valid: bool


def build_entry_plan(
    *,
    price: float,
    avg_whale_price: float,
    support: float,
    resistance: float,
    volume_spike: bool,
    whale_inflow: bool,
    min_risk_reward: float = 2.0,
) -> EntryPlan | None:
    """Build a shared entry plan for strategy reports."""
    if avg_whale_price <= 0 or support <= 0 or resistance <= 0:
        return None
    if not volume_spike or not whale_inflow:
        return None

    entry_low = support
    entry_high = avg_whale_price
    stop_loss = support * 0.97
    take_profit_1 = resistance
    take_profit_2 = resistance * 1.2
    entry = (entry_low + entry_high) / 2
    risk = entry - stop_loss
    reward = take_profit_1 - entry
    risk_reward = reward / risk if risk > 0 else 0.0
    breakout_entry = resistance if price > resistance and volume_spike else None
    return EntryPlan(
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,
        risk_reward=risk_reward,
        breakout_entry=breakout_entry,
        is_valid=risk_reward >= min_risk_reward,
    )
