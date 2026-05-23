"""Entry point for running the notification scheduler."""

import logging
import time

from src.core.discord import DiscordConnector
from src.core.registry import StrategyScheduler
from src.core.scheduler import scheduler

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


if __name__ == "__main__":
    try:
        DiscordConnector().send_message("TEST", "```Boot check: scheduler about to start```")
    except Exception:
        logger.exception("Failed to send boot check message.")

    strategy_scheduler = StrategyScheduler()
    strategy_scheduler.schedule()
    strategy_scheduler.bootstrap()

    scheduler.start()

    print("Scheduler is running...")

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down scheduler...")
        scheduler.shutdown()
