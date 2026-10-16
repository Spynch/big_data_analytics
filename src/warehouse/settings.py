"""Configuration shared by container jobs and Airflow tasks."""
import os
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]


def setting(name, default=None):
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise ValueError(f"Missing configuration: {name}")
    return value


def pg_params(target="source", admin=False):
    if target == "source":
        return dict(host="postgres-source", dbname=setting("SOURCE_DB"),
                    user=setting("SOURCE_ADMIN" if admin else "SOURCE_ETL_USER"),
                    password=setting("SOURCE_PASSWORD" if admin else "SOURCE_ETL_PASSWORD"))
    if target == "meta":
        return dict(host="postgres-meta", dbname="postgres", user=setting("META_ADMIN"),
                    password=setting("META_PASSWORD"))
    return dict(host="postgres-meta", dbname="warehouse_control", user="warehouse_control",
                password=setting("CONTROL_DB_PASSWORD"))


def sqlalchemy_url(target):
    if target == "clickhouse":
        return (f"clickhousedb://{quote(setting('CLICKHOUSE_USER'), safe='')}:"
                f"{quote(setting('CLICKHOUSE_PASSWORD'), safe='')}@clickhouse:8123/default")
    p = pg_params(target, admin=True)
    return (f"postgresql+psycopg://{quote(p['user'], safe='')}:"
            f"{quote(p['password'], safe='')}@{p['host']}/{p['dbname']}")
