import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from .connections import postgres


def batch_for(run_id):
    return str(uuid5(NAMESPACE_URL, "warehouse_pipeline/" + run_id))


def start_batch(run_id):
    batch = batch_for(run_id)
    with postgres("control") as conn:
        conn.execute("INSERT INTO batches(batch_id,run_id,status) VALUES (%s,%s,'running') "
                     "ON CONFLICT(batch_id) DO UPDATE SET status='running',error=NULL,finished_at=NULL", (batch,run_id))
    return batch


def fail_batch(batch, error):
    with postgres("control") as conn:
        conn.execute("UPDATE batches SET status='failed',error=%s,finished_at=clock_timestamp() WHERE batch_id=%s",
                     (str(error)[:4000],batch))


def record_dataset(batch, dataset, count, snapshot=None, extracted=None):
    with postgres("control") as conn:
        conn.execute("INSERT INTO dataset_loads(batch_id,dataset,row_count,snapshot_id,extracted_at) "
                     "VALUES(%s,%s,%s,%s,%s) ON CONFLICT(batch_id,dataset) DO UPDATE SET "
                     "row_count=excluded.row_count,snapshot_id=excluded.snapshot_id,"
                     "extracted_at=excluded.extracted_at,completed_at=clock_timestamp()",
                     (batch,dataset,count,snapshot,extracted))


def clear_datasets(batch, names):
    with postgres("control") as conn:
        conn.execute("DELETE FROM dataset_loads WHERE batch_id=%s AND dataset=ANY(%s)", (batch,list(names)))


def require_datasets(batch, names):
    with postgres("control") as conn:
        found = {r[0]:r[1:] for r in conn.execute(
            "SELECT dataset,row_count,snapshot_id FROM dataset_loads WHERE batch_id=%s", (batch,))}
    missing = set(names)-set(found)
    if missing:
        raise ValueError(f"Incomplete batch {batch}: {sorted(missing)}")
    return found


def canonical(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k:canonical(v) for k,v in value.items()}
    if isinstance(value, (tuple,list)):
        return [canonical(v) for v in value]
    return value


def row_digest(rows):
    encoded = [json.dumps(canonical(row), ensure_ascii=False, separators=(",",":"), sort_keys=True) for row in rows]
    return hashlib.sha256("\n".join(sorted(encoded)).encode()).hexdigest()
