"""Environment configuration utilities for Discord webhooks."""

import os
from typing import Final

from dotenv import load_dotenv

load_dotenv()


class Env:
    """Expose Discord webhook URLs sourced from environment variables."""

    DISCORD_CHANNEL_TEST: Final[str | None] = os.getenv("DISCORD_CHANNEL_TEST")
    DISCORD_CHANNEL_VOLUMEBOMB: Final[str | None] = os.getenv("DISCORD_CHANNEL_VOLUMEBOMB")
    DISCORD_CHANNEL_CRITICAL: Final[str | None] = os.getenv("DISCORD_CHANNEL_CRITICAL")
    DISCORD_CHANNEL_OI: Final[str | None] = os.getenv("DISCORD_CHANNEL_OI")

    @classmethod
    def validate(cls) -> None:
        """Validate required environment variables are available."""
        required_vars: dict[str, str | None] = {
            "DISCORD_CHANNEL_TEST": cls.DISCORD_CHANNEL_TEST,
            "DISCORD_CHANNEL_VOLUMEBOMB": cls.DISCORD_CHANNEL_VOLUMEBOMB,
            "DISCORD_CHANNEL_CRITICAL": cls.DISCORD_CHANNEL_CRITICAL,
            "DISCORD_CHANNEL_OI": cls.DISCORD_CHANNEL_OI,
        }

        missing_vars = [var for var, value in required_vars.items() if not value]
        if missing_vars:
            joined = ", ".join(missing_vars)
            raise ValueError(f"Missing required environment variables: {joined}")


Env.validate()
