import json


class Config:
    _configInstances = {}

    def __new__(cls, config_file_path):
        if config_file_path not in cls._configInstances:
            cls._configInstances[config_file_path] = super(Config, cls).__new__(cls)
            instance = cls._configInstances[config_file_path]
            with open(config_file_path, "r") as f:
                instance.config = json.load(f)
        return cls._configInstances[config_file_path].config
