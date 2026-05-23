"""Environment configuration utilities."""

import os
from typing import Final

from dotenv import load_dotenv

from src.core.config_reader import Config
from src.core.paths import get_notification_config_path

load_dotenv()


class Env:
    """Expose runtime settings sourced from environment variables."""

    DISCORD_CHANNEL_TEST: Final[str | None] = os.getenv("DISCORD_CHANNEL_TEST")
    DISCORD_CHANNEL_CRITICAL: Final[str | None] = os.getenv("DISCORD_CHANNEL_CRITICAL")
    DISCORD_CHANNEL_ACCUMULATION: Final[str | None] = os.getenv("DISCORD_CHANNEL_ACCUMULATION")
    DISCORD_CHANNEL_FIVE_FACTOR: Final[str | None] = os.getenv("DISCORD_CHANNEL_FIVE_FACTOR")
    OPENROUTER_API_KEY: Final[str | None] = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_MODEL: Final[str] = os.getenv("OPENROUTER_MODEL", "openrouter/free")

    @classmethod
    def validate(cls) -> None:
        """Validate required environment variables are available."""
        required_vars: dict[str, str | None] = {
            "DISCORD_CHANNEL_TEST": cls.DISCORD_CHANNEL_TEST,
            "DISCORD_CHANNEL_CRITICAL": cls.DISCORD_CHANNEL_CRITICAL,
        }
        notification_config = Config(get_notification_config_path())
        if _strategy_enabled(notification_config, "Accumulation"):
            required_vars["DISCORD_CHANNEL_ACCUMULATION"] = cls.DISCORD_CHANNEL_ACCUMULATION
        if _strategy_enabled(notification_config, "FiveFactor"):
            required_vars["DISCORD_CHANNEL_FIVE_FACTOR"] = cls.DISCORD_CHANNEL_FIVE_FACTOR

        missing_vars = [var for var, value in required_vars.items() if not value]
        if missing_vars:
            joined = ", ".join(missing_vars)
            raise ValueError(f"Missing required environment variables: {joined}")


def _strategy_enabled(notification_config: dict[str, object], strategy_name: str) -> bool:
    strategy_config = notification_config.get(strategy_name, {})
    if not isinstance(strategy_config, dict):
        return False
    return bool(strategy_config.get("enabled", False))


Env.validate()
