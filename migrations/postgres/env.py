from alembic import context
from sqlalchemy import create_engine, text
from warehouse.settings import sqlalchemy_url

engine = create_engine(sqlalchemy_url("source"))
with engine.connect() as connection:
    connection.execute(text("CREATE SCHEMA IF NOT EXISTS migration_meta"))
    connection.commit()
    connection.execute(text("SELECT pg_advisory_lock(914001)"))
    connection.commit()
    try:
        context.configure(connection=connection, version_table_schema="migration_meta")
        with context.begin_transaction():
            context.run_migrations()
    finally:
        connection.execute(text("SELECT pg_advisory_unlock(914001)"))
        connection.commit()
