import os
from pathlib import Path

from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[2]


class Settings:
    def __init__(self, values):
        self.values = values

    @classmethod
    def from_env(cls):
        return cls(os.environ)

    def get(self, key):
        return self.values[key]

    def dsn(self, target):
        prefix = "SOURCE" if target == "source" else "DWH"
        return make_conninfo(
            host=self.get(f"{prefix}_HOST"),
            port=int(self.values.get(f"{prefix}_CONNECT_PORT", "5432")),
            dbname=self.get(f"{prefix}_DB"),
            user=self.get(f"{prefix}_USER"),
            password=self.get(f"{prefix}_PASSWORD"),
            connect_timeout=10,
        )
