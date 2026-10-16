"""External CDM only; business rows remain in MinIO."""
import json
import re
from pathlib import Path
from alembic import op
from sqlalchemy import text
from warehouse.settings import setting

revision = "ch_0001"
down_revision = None


def upgrade():
    op.execute("CREATE DATABASE IF NOT EXISTS cdm")
    definitions = json.loads((Path(__file__).parent / "0001_columns.json").read_text())
    for name, columns in definitions.items():
        url = f"{setting('S3_ENDPOINT').rstrip('/')}/{setting('S3_BUCKET')}/cdm/{name}/current.parquet"
        if "'" in url:
            raise ValueError("Invalid S3 URL")
        op.execute(f"CREATE TABLE IF NOT EXISTS cdm.{name} ({columns}) "
                   f"ENGINE = S3(warehouse_s3, url='{url}', format='Parquet')")
        actual = op.get_bind().execute(text(f"SELECT engine FROM system.tables WHERE database='cdm' AND name='{name}'")).scalar()
        if actual != "S3":
            raise ValueError(f"Unexpected engine for {name}: {actual}")
    # Passwords are bound by the driver, never stored in migration SQL.
    from warehouse.connections import clickhouse
    with clickhouse() as client:
        user = setting("CLICKHOUSE_READ_USER")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", user):
            raise ValueError("Invalid ClickHouse reader name")
        client.command("CREATE USER IF NOT EXISTS {user:Identifier} IDENTIFIED WITH sha256_password BY {password:String}",
                       parameters={"user":user,"password":setting("CLICKHOUSE_READ_PASSWORD")})
        client.command(f"GRANT SELECT ON cdm.* TO `{user}`")
        client.command(f"ALTER USER `{user}` SETTINGS PROFILE reports")


def downgrade():
    raise RuntimeError("CDM definitions must be evolved with forward revisions")
