import time
from src.core.scheduler import scheduler
from src.notifier.scheduler import NotificationScheduler
from src.core.discord import DiscordConnector

if __name__ == "__main__":
    try:
        DiscordConnector().send_message("TEST", "```Boot check: scheduler about to start```")
    except Exception:
        pass

    NotificationScheduler().schedule()

    scheduler.start()

    print("Scheduler is running...")

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down scheduler...")
        scheduler.shutdown()
