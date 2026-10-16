"""Read-only state fingerprint, excluding runtime timestamps and credentials."""
import hashlib
import json

from . import connections as db
from .contracts import CDM, PG
from .control import canonical
from .pipeline import SORT_KEYS
from .settings import setting


def fingerprint():
    result = {}
    with db.postgres() as conn:
        result['source_rows'] = {f'{s}.{t}':conn.execute(f'SELECT count(*) FROM "{s}"."{t}"').fetchone()[0]
                                 for s,t,_,_ in PG.values()}
    with db.postgres(admin=True) as conn:
        result['postgres_revision'] = conn.execute('SELECT version_num FROM migration_meta.alembic_version').fetchone()[0]
    with db.postgres('control') as conn:
        result['control_revision'] = conn.execute('SELECT version_num FROM alembic_version').fetchone()[0]
        result['lake_revisions'] = conn.execute('SELECT version,checksum,status FROM lake_migrations ORDER BY version').fetchall()
        result['batches'] = [(str(b),s) for b,s in conn.execute('SELECT batch_id,status FROM batches ORDER BY batch_id')]
    from bson import json_util
    with db.mongo() as client:
        result['mongo'] = {n:hashlib.sha256(json_util.dumps(list(client[setting('MONGO_DB')][n].find().sort('_id',1)),
                          json_options=json_util.CANONICAL_JSON_OPTIONS,sort_keys=True).encode()).hexdigest()
                           for n in ['clients','orders','restaurant']}
    cat = db.catalog()
    result['tables'] = {}
    for namespace in ['stg','dds']:
        for identifier in cat.list_tables(namespace):
            table = cat.load_table(identifier)
            result['tables']['.'.join(identifier)] = [str(table.metadata.table_uuid),table.metadata.current_snapshot_id]
    with db.clickhouse() as client:
        result['clickhouse_revision'] = client.query('SELECT version_num FROM migration_meta.alembic_version').first_row[0]
        result['marts'] = {}
        for name in CDM:
            rows = client.query(f"SELECT * FROM cdm.{name} ORDER BY {','.join(SORT_KEYS[name])}").result_rows
            result['marts'][name] = hashlib.sha256(json.dumps(canonical(rows),ensure_ascii=False).encode()).hexdigest()
    return result
