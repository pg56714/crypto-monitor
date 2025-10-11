import json


class Config:
    _config_cache = {}

    def __new__(cls, config_file_path):
        if config_file_path not in cls._config_cache:
            with open(config_file_path, "r") as f:
                config_data = json.load(f)
            cls._config_cache[config_file_path] = config_data
        return cls._config_cache[config_file_path]
