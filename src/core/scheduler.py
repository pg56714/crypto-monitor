from src.core.discord import DiscordConnector
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from datetime import datetime
import traceback
import asyncio

# 設定最大同時 30 條執行緒
executors = {"default": ThreadPoolExecutor(30)}

# 若有多個任務堆積，只執行一次
# 任務錯過執行時間時的容錯時間（None 代表不限制）
job_defaults = {
    "coalesce": True,
    "misfire_grace_time": None,
}

scheduler = BackgroundScheduler(
    job_defaults=job_defaults,
    executors=executors,
)


class BaseScheduler(object):
    def __init__(self):
        self.discord = DiscordConnector()

    def _format_error_message(self, job_class, exception: Exception) -> str:
        return (
            f"```"
            f"Error: {job_class.__name__} failed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{traceback.format_exc()[-1900:]}\n"
            f"```"
        )

    def execute_sync_job(self, job_class, channel: str = "CRITICAL"):
        try:
            job_class().run()
        except Exception as e:
            message = self._format_error_message(job_class, e)
            self.discord.send_message(channel, message)

    def execute_async_job(self, job_class, channel: str = "CRITICAL"):
        try:
            asyncio.run(job_class().run())
        except Exception as e:
            message = self._format_error_message(job_class, e)
            self.discord.send_message(channel, message)
