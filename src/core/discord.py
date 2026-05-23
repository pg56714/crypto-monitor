"""Utilities for sending messages via Discord webhooks."""

from discord import SyncWebhook

from src.config.env_config import Env


class DiscordConnector:
    """Provide a simple interface for dispatching Discord webhook messages."""

    def __init__(self) -> None:
        self.webhooks: dict[str, str | None] = {
            "TEST": Env.DISCORD_CHANNEL_TEST,
            "CRITICAL": Env.DISCORD_CHANNEL_CRITICAL,
            "ACCUMULATION": Env.DISCORD_CHANNEL_ACCUMULATION,
            "FIVE_FACTOR": Env.DISCORD_CHANNEL_FIVE_FACTOR,
        }

    def send_message(self, channel: str, message: str) -> None:
        """Send `message` to the Discord webhook configured for `channel`."""
        webhook_url = self.webhooks.get(channel.upper())
        if not webhook_url:
            raise ValueError(f"Invalid Discord channel or missing webhook: {channel}")

        webhook = SyncWebhook.from_url(webhook_url)
        webhook.send(message)
