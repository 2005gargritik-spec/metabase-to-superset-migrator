import json
import os

class Config:

    def __init__(self, filename="config.json"):

        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_dir, filename)

        with open(config_path, "r") as f:
            self.data = json.load(f)

    @property
    def metabase(self):
        return self.data["metabase"]

    @property
    def superset(self):
        return self.data["superset"]

    @property
    def defaults(self):
        return self.data["defaults"]

    @property
    def output(self):
        return self.data["output"] 