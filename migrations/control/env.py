from alembic import context
from sqlalchemy import create_engine, text
from warehouse.settings import sqlalchemy_url

engine = create_engine(sqlalchemy_url("control"))
with engine.connect() as connection:
    connection.execute(text("SELECT pg_advisory_lock(914002)"))
    connection.commit()
    try:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    finally:
        connection.execute(text("SELECT pg_advisory_unlock(914002)"))
        connection.commit()
