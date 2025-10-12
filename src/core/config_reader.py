"""Shared configuration loader with caching support."""

import json
from pathlib import Path
from typing import Any, ClassVar

ConfigData = dict[str, Any]


class Config:
    """Cache JSON configuration files keyed by their path."""

    _config_cache: ClassVar[dict[Path | str, ConfigData]] = {}

    def __new__(cls, config_file_path: str | Path) -> ConfigData:
        """Load and cache configuration data for the provided file path."""
        if config_file_path not in cls._config_cache:
            path = Path(config_file_path)
            with path.open(encoding="utf-8") as config_file:
                config_data: ConfigData = json.load(config_file)
            cls._config_cache[config_file_path] = config_data
        return cls._config_cache[config_file_path]
