import logging
from datetime import datetime, timezone

import psycopg

from airflow_utils.loader import load_stg
from airflow_utils.mongo_source import extract_mongo
from airflow_utils.postgres_source import extract_postgres_events
from warehouse.config import ROOT, Settings
from warehouse.csv_import import import_csvs

logger = logging.getLogger(__name__)


def import_external_csvs(settings):
    with psycopg.connect(settings.dsn("source")) as connection:
        import_csvs(connection, ROOT / "seeds" / "csv", settings.get("SOURCE_TIMEZONE"))


def refresh_warehouse(settings):
    with psycopg.connect(settings.dsn("warehouse")) as connection:
        extracted_at = datetime.now(timezone.utc)
        last_loaded_id = connection.execute(
            "SELECT coalesce(max(id), 0) FROM stg.pg_logs"
        ).fetchone()[0]
        postgres_events = extract_postgres_events(settings, last_loaded_id)
        mongo = extract_mongo(settings)
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        applied_events = load_stg(connection, postgres_events, mongo, extracted_at)
        connection.execute((ROOT / "sql" / "dds" / "rebuild.sql").read_text(encoding="utf-8"))
        logger.info(
            "Warehouse refresh committed: PostgreSQL events=%s MongoDB=%s",
            applied_events,
            {name: len(rows) for name, rows in mongo.items()},
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    import_external_csvs(settings)
    refresh_warehouse(settings)
