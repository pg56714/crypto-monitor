"""Common filesystem paths shared across the project."""

from pathlib import Path

ROOT: Path = Path(__file__).resolve().parents[2]
CONFIG_DIR: Path = ROOT / "src" / "config"
NOTIFICATION_CONFIG_PATH: Path = CONFIG_DIR / "notification.json"


def get_notification_config_path() -> Path:
    """Return the absolute path to the notification configuration file."""
    return NOTIFICATION_CONFIG_PATH
