"""Tasks that register notifier jobs with the shared scheduler."""

from src.core.scheduler import BaseScheduler, scheduler
from src.notifier.oi import OI
from src.notifier.volumebomb import VolumeBomb


class NotificationScheduler(BaseScheduler):
    """Wire notification jobs into the global scheduler."""

    def __init__(self) -> None:
        super().__init__()

    def schedule(self) -> None:
        """Register recurring jobs for the available notifiers."""
        scheduler.add_job(
            self.execute_async_job,
            "cron",
            minute="*/5",
            second=0,
            args=[VolumeBomb],
        )
        scheduler.add_job(
            self.execute_async_job,
            "cron",
            minute="*/5",
            second=10,
            args=[OI],
        )
