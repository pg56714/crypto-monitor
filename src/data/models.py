"""Shared data models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TokenAnnouncement:
    """A normalized token announcement event."""

    source_id: str
    symbol: str
    title: str
    url: str


@dataclass(frozen=True)
class DerivativesSnapshot:
    """Normalized derivatives metrics for one symbol."""

    symbol: str
    funding_rate: float
    open_interest_usd: float
    long_short_ratio: float | None = None


@dataclass(frozen=True)
class MarketSnapshot:
    """Normalized market metrics for one symbol."""

    symbol: str
    price: float
    price_change_pct: float
    quote_volume: float


@dataclass(frozen=True)
class WalletFlow:
    """Normalized wallet flow metrics."""

    address: str
    symbol: str
    net_value_usd: float
