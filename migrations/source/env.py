from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from warehouse.config import Settings

settings = context.config.attributes.get('settings') or Settings.from_env()
engine = create_engine(settings.migration_url('source'), poolclass=NullPool)
with engine.connect() as connection:
    connection.exec_driver_sql('CREATE SCHEMA IF NOT EXISTS migration_meta')
    connection.commit()
    context.configure(connection=connection, version_table_schema='migration_meta')
    with context.begin_transaction():
        context.run_migrations()
