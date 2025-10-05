from discord import SyncWebhook
from src.config.env_config import Env


class DiscordConnector:
    def __init__(self):
        self.webhooks = {
            "VOLUMEBOMB": Env.DISCORD_CHANNEL_VOLUMEBOMB,
            "CRITICAL": Env.DISCORD_CHANNEL_CRITICAL,
            "TEST": Env.DISCORD_CHANNEL_TEST,
        }

    def send_message(self, channel, message):
        webhook_url = self.webhooks.get(channel.upper())
        if not webhook_url:
            raise ValueError(f"Invalid Discord channel: {channel}")

        webhook = SyncWebhook.from_url(webhook_url)
        webhook.send(message)
