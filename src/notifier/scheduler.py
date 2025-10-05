from src.core.scheduler import scheduler
from src.core.scheduler import BaseScheduler

from src.notifier.volumebomb import VolumeBomb


class NotificationScheduler(BaseScheduler):
    def __init__(self):
        super().__init__()

    def schedule(self):
        scheduler.add_job(self.execute_async_job, "cron", minute="*/5", second=0, args=[VolumeBomb])
