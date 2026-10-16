from alembic import context
from sqlalchemy import create_engine, text
import clickhouse_connect.cc_sqlalchemy.alembic  # registers ClickHouseImpl
from warehouse.connections import postgres
from warehouse.settings import sqlalchemy_url

with postgres("control", autocommit=True) as lock:
    lock.execute("SELECT pg_advisory_lock(914004)")
    try:
        with create_engine(sqlalchemy_url("clickhouse")).connect() as connection:
            connection.execute(text("CREATE DATABASE IF NOT EXISTS migration_meta"))
            context.configure(connection=connection, version_table_schema="migration_meta", transactional_ddl=False)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        lock.execute("SELECT pg_advisory_unlock(914004)")
