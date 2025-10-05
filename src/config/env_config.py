import os
from dotenv import load_dotenv

load_dotenv()


class Env:
    # Discord
    DISCORD_CHANNEL_TEST = os.getenv("DISCORD_CHANNEL_TEST")
    DISCORD_CHANNEL_VOLUMEBOMB = os.getenv("DISCORD_CHANNEL_VOLUMEBOMB")
    DISCORD_CHANNEL_CRITICAL = os.getenv("DISCORD_CHANNEL_CRITICAL")
    DISCORD_CHANNEL_OI = os.getenv("DISCORD_CHANNEL_OI")

    @classmethod
    def validate(cls):
        required_vars = {
            "DISCORD_CHANNEL_TEST": cls.DISCORD_CHANNEL_TEST,
            "DISCORD_CHANNEL_VOLUMEBOMB": cls.DISCORD_CHANNEL_VOLUMEBOMB,
            "DISCORD_CHANNEL_CRITICAL": cls.DISCORD_CHANNEL_CRITICAL,
            "DISCORD_CHANNEL_OI": cls.DISCORD_CHANNEL_OI,
        }

        missing_vars = [var for var, value in required_vars.items() if not value]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")


Env.validate()
