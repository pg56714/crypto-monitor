"""Scheduler helpers for orchestrating notification jobs."""

import asyncio
import traceback
from datetime import UTC, datetime
from typing import Protocol

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler

from src.core.discord import DiscordConnector

executors = {"default": ThreadPoolExecutor(30)}

job_defaults = {
    "coalesce": True,
    "misfire_grace_time": None,
}

scheduler = BackgroundScheduler(
    job_defaults=job_defaults,
    executors=executors,
    timezone=UTC,
)


class AsyncJob(Protocol):
    """Protocol representing an asynchronous job."""

    async def run(self) -> None:
        """Execute the job."""


class BaseScheduler:
    """Shared helpers for scheduling monitor jobs and dispatching errors."""

    def __init__(self) -> None:
        self.discord = DiscordConnector()

    def _format_error_message(self, job_class: type[object], exception: Exception) -> str:
        """Construct a formatted Discord message for job failures."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        traceback_snippet = traceback.format_exc()[-1900:]
        return f"```Error: {job_class.__name__} failed at {timestamp}\n{traceback_snippet}\n```"

    def execute_async_job(self, job_class: type[AsyncJob], channel: str = "CRITICAL") -> None:
        """Run an asynchronous job and report failures to Discord."""
        try:
            asyncio.run(job_class().run())
        except Exception as exc:  # noqa: BLE001 - capture all to notify operators
            message = self._format_error_message(job_class, exc)
            self.discord.send_message(channel, message)
