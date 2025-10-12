"""Utilities for sending messages via Discord webhooks."""

from discord import SyncWebhook

from src.config.env_config import Env


class DiscordConnector:
    """Provide a simple interface for dispatching Discord webhook messages."""

    def __init__(self) -> None:
        self.webhooks: dict[str, str | None] = {
            "TEST": Env.DISCORD_CHANNEL_TEST,
            "VOLUMEBOMB": Env.DISCORD_CHANNEL_VOLUMEBOMB,
            "CRITICAL": Env.DISCORD_CHANNEL_CRITICAL,
            "OI": Env.DISCORD_CHANNEL_OI,
        }

    def send_message(self, channel: str, message: str) -> None:
        """Send `message` to the Discord webhook configured for `channel`."""
        webhook_url = self.webhooks.get(channel.upper())
        if not webhook_url:
            raise ValueError(f"Invalid Discord channel: {channel}")

        webhook = SyncWebhook.from_url(webhook_url)
        webhook.send(message)
