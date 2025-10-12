"""Entry point for running the notification scheduler."""

import logging
import time

from src.core.discord import DiscordConnector
from src.core.scheduler import scheduler
from src.notifier.scheduler import NotificationScheduler

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


if __name__ == "__main__":
    try:
        DiscordConnector().send_message("TEST", "```Boot check: scheduler about to start```")
    except Exception:
        logger.exception("Failed to send boot check message.")

    NotificationScheduler().schedule()

    scheduler.start()

    print("Scheduler is running...")

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down scheduler...")
        scheduler.shutdown()
