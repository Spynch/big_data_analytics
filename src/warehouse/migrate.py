"""Versioned migrations; no migrations are run by the ordinary pipeline."""
import hashlib
import json

from .connections import catalog, postgres
from .contracts import arrow_schema
from .settings import ROOT


def lake():
    import pyarrow as pa
    cat = catalog()
    with postgres("control", autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(914003)")
        try:
            for path in sorted((ROOT / "migrations/lake").glob("*.json")):
                checksum = hashlib.sha256(path.read_bytes()).hexdigest()
                prior = conn.execute("SELECT checksum,status FROM lake_migrations WHERE version=%s", (path.stem,)).fetchone()
                if prior and prior[0] != checksum:
                    raise ValueError(f"Applied migration checksum mismatch: {path.name}")
                definition = json.loads(path.read_text())
                conn.execute("INSERT INTO lake_migrations(version,checksum,status) VALUES(%s,%s,'running') "
                             "ON CONFLICT(version) DO UPDATE SET status='running',error=NULL", (path.stem,checksum))
                try:
                    for identifier,fields in definition.items():
                        namespace,name = identifier.split(".")
                        expected = arrow_schema(fields)
                        # Constraints are enforced explicitly by ETL (Iceberg does not enforce foreign keys).
                        if namespace == "dds":
                            expected = pa.schema([field.with_nullable(True) for field in expected])
                        if (namespace,name) not in cat.list_tables(namespace):
                            cat.create_table((namespace,name),schema=expected,properties={
                                "format-version":"2", "write.format.default":"parquet",
                                "write.target-file-size-bytes":"16777216"})
                        actual = cat.load_table((namespace,name)).schema().as_arrow()
                        if not actual.equals(expected,check_metadata=False):
                            # Arrow's Iceberg conversion may expose large_string instead of string.
                            def signature(schema):
                                return [(f.name, str(pa.string() if pa.types.is_large_string(f.type) else f.type),
                                         f.nullable) for f in schema]
                            if signature(actual) != signature(expected):
                                raise ValueError(f"Schema drift in {identifier}: {actual}")
                    conn.execute("UPDATE lake_migrations SET status='success',completed_at=clock_timestamp() WHERE version=%s", (path.stem,))
                except Exception as exc:
                    conn.execute("UPDATE lake_migrations SET status='failed',error=%s WHERE version=%s",(str(exc)[:4000],path.stem))
                    raise
        finally:
            conn.execute("SELECT pg_advisory_unlock(914003)")


def run(target):
    if target == "lake":
        return lake()
    from alembic import command
    from alembic.config import Config
    command.upgrade(Config(str(ROOT / f"alembic-{target}.ini")), "head")
    if target == "postgres":
        from .bootstrap import source_grants
        source_grants()
