"""Register strategy jobs with the shared scheduler."""

from typing import Any

from src.core.config_reader import Config
from src.core.paths import get_notification_config_path
from src.core.scheduler import BaseScheduler, scheduler
from src.strategies.accumulation_pool import POOL, AccumulationPool
from src.strategies.accumulation_scanner import AccumulationScanner
from src.strategies.five_factor import FiveFactor


class StrategyScheduler(BaseScheduler):
    """Wire strategy jobs into the global scheduler."""

    def __init__(self) -> None:
        super().__init__()
        self.config: dict[str, Any] = Config(get_notification_config_path())

    def schedule(self) -> None:
        """Register cron jobs for strategies enabled in the notification config."""
        if self._is_enabled("FiveFactor"):
            scheduler.add_job(
                self.execute_async_job,
                "cron",
                minute="*/5",
                second=10,
                args=[FiveFactor],
            )
        if self._is_enabled("Accumulation"):
            scheduler.add_job(
                self.execute_async_job,
                "cron",
                hour=18,
                minute=0,
                second=0,
                args=[AccumulationPool],
            )
            scheduler.add_job(
                self.execute_async_job,
                "cron",
                minute=30,
                second=0,
                args=[AccumulationScanner],
            )

    def bootstrap(self) -> None:
        """Initialize process-local strategy state before scheduled scans begin."""
        if self._is_enabled("Accumulation") and not POOL:
            self.execute_async_job(AccumulationPool)

    def _is_enabled(self, strategy_name: str, *, default: bool = False) -> bool:
        """Return whether a strategy is enabled in notification configuration."""
        strategy_config = self.config.get(strategy_name, {})
        if not isinstance(strategy_config, dict):
            return default
        return bool(strategy_config.get("enabled", default))
