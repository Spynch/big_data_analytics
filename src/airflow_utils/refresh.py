import logging
from datetime import datetime, timezone

import psycopg

from airflow_utils.loader import load_stg
from airflow_utils.mongo_source import extract_mongo
from airflow_utils.postgres_source import extract_postgres_events
from airflow_utils.validation import validate_warehouse
from warehouse.config import ROOT, Settings

WRITER_LOCK = 7350192601
logger = logging.getLogger(__name__)


def refresh_warehouse(settings):
    with psycopg.connect(settings.dsn('warehouse'), autocommit=True) as connection:
        if not connection.execute('SELECT pg_try_advisory_lock(%s)', (WRITER_LOCK,)).fetchone()[0]:
            raise RuntimeError('Another warehouse refresh is running')
        extracted_at = datetime.now(timezone.utc)
        loaded_log_ids = {
            row[0] for row in connection.execute('SELECT id FROM stg.pg_logs').fetchall()
        }
        postgres_events = extract_postgres_events(settings, loaded_log_ids)
        mongo = extract_mongo(settings)
        with connection.transaction():
            connection.execute("SET LOCAL TIME ZONE 'UTC'")
            connection.execute("SELECT set_config('warehouse.source_timezone', %s, true)",
                               (settings.get('SOURCE_TIMEZONE'),))
            applied_events = load_stg(connection, postgres_events, mongo, extracted_at)
            for filename in ('validate_sources.sql', 'rebuild.sql'):
                connection.execute((ROOT / 'sql' / 'dds' / filename).read_text(encoding='utf-8'))
            validate_warehouse(connection)
        logger.info('Warehouse refresh committed: PostgreSQL events=%s MongoDB=%s',
                    applied_events,
                    {name: len(rows) for name, rows in mongo.items()})


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    refresh_warehouse(Settings.from_env())
