import json
import os


DEFAULT_CONFIG = "~/.paulobot.json"


class Config:
    def __init__(self):
        self.data = None
        self._load_config(os.path.expanduser(DEFAULT_CONFIG))

    def _load_config(self, path):
        if not os.path.exists(path):
            raise Exception(f"Cannot find config file {path}")

        with open(path, 'r') as f:
            self.data = json.load(f)