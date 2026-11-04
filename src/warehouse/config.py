import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    values: dict[str, str]

    @classmethod
    def from_env(cls):
        settings = cls(dict(os.environ))
        ZoneInfo(settings.get("SOURCE_TIMEZONE"))
        return settings

    def get(self, key):
        value = self.values.get(key)
        if not value:
            raise ValueError(f"Missing setting: {key}")
        return value

    def pg_params(self, target):
        prefix = "SOURCE" if target == "source" else "DWH"
        return dict(
            host=self.get(f"{prefix}_HOST"),
            port=int(self.values.get(f"{prefix}_CONNECT_PORT", "5432")),
            dbname=self.get(f"{prefix}_DB"),
            user=self.get(f"{prefix}_USER"),
            password=self.get(f"{prefix}_PASSWORD"),
            connect_timeout=10,
        )

    def dsn(self, target):
        return make_conninfo(**self.pg_params(target))
