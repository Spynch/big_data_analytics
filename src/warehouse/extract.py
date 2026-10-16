"""Bounded extraction; one PostgreSQL snapshot and atomic per-table Iceberg commits."""
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from psycopg import sql
from psycopg.rows import dict_row

from .connections import catalog, mongo, postgres
from .contracts import MONGO, PG, STG, arrow_schema
from .control import clear_datasets, record_dataset
from .settings import setting

CHUNK = 1000


def parse_time(value):
    if value is None or isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            try:
                result = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError as exc:
                raise ValueError(f"Unsupported date/time: {value!r}") from exc
    else:
        raise ValueError(f"Unsupported date/time type: {type(value).__name__}")
    if result is not None:
        if result.tzinfo is None:
            zone = ZoneInfo(setting("SOURCE_TIMEZONE", "UTC"))
            first, second = result.replace(tzinfo=zone, fold=0), result.replace(tzinfo=zone, fold=1)
            if first.utcoffset() != second.utcoffset():
                raise ValueError(f"Ambiguous or nonexistent local time: {value!r}")
            result = first
        return result.astimezone(timezone.utc)
    return None


def decimal(value):
    from bson import Decimal128
    if isinstance(value, float):
        raise ValueError("BSON floating money is ambiguous; use Decimal128 or a decimal string")
    return value.to_decimal() if isinstance(value, Decimal128) else Decimal(value)


def write_snapshot(cat, name, batch, batches):
    import pyarrow as pa
    from pyiceberg.expressions import AlwaysTrue, EqualTo
    table = cat.load_table(("stg", name))
    schema = arrow_schema(STG[name])
    count = 0
    def reader():
        nonlocal count
        for rows in batches:
            count += len(rows)
            yield pa.RecordBatch.from_pylist(rows, schema=schema)
    table.overwrite(pa.RecordBatchReader.from_batches(schema, reader()),
                    overwrite_filter=AlwaysTrue() if name == "pg_logs" else EqualTo("batch_id",batch))
    table.refresh()
    return count, table.current_snapshot().snapshot_id if table.current_snapshot() else None


def postgres_snapshot(batch):
    names = ["stg."+name for name in PG]
    clear_datasets(batch,names)
    cat = catalog()
    completed = []
    with postgres(row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        conn.execute("SET LOCAL TIME ZONE 'UTC'")
        extracted = conn.execute("SELECT transaction_timestamp() AS ts").fetchone()["ts"]
        for name,(schema,table,pk,fields) in PG.items():
            with conn.cursor(name="snapshot_" + name) as cursor:
                extra = ",object_value::text AS __object_value" if name == "pg_logs" else ""
                cursor.execute(sql.SQL("SELECT t.*,to_jsonb(t)::text AS __payload" + extra + " FROM {}.{} t ORDER BY {}").format(
                    sql.Identifier(schema),sql.Identifier(table),sql.Identifier(pk)))
                def chunks():
                    while rows := cursor.fetchmany(CHUNK):
                        out = []
                        for row in rows:
                            payload = row.pop("__payload")
                            source_pk = str(row[pk])
                            if name == "pg_logs":
                                row["log_id"] = row.pop("id")
                                # Keep PostgreSQL's exact JSON numeric representation, not a float roundtrip.
                                row["object_value"] = row.pop("__object_value")
                            row.update(batch_id=batch,source_system="postgres",source_schema=schema,
                                       source_pk=source_pk,extracted_at=extracted,payload=payload)
                            out.append(row)
                        yield out
                count,snapshot = write_snapshot(cat,name,batch,chunks())
                completed.append((name,count,snapshot))
    for name,count,snapshot in completed:
        record_dataset(batch,"stg."+name,count,snapshot,extracted)
    return {"batch_id":batch,"datasets":len(completed)}


def mongo_snapshot(batch):
    from bson import json_util
    clear_datasets(batch,["stg."+name for name in MONGO])
    cat = catalog()
    completed = []
    with mongo() as client:
        db = client[setting("MONGO_DB")]
        for name,(collection,fields) in MONGO.items():
            extracted = datetime.now(timezone.utc)
            def chunks():
                rows = []
                with db[collection].find().sort("_id",1).batch_size(CHUNK) as cursor:
                    for document in cursor:
                        row = dict(batch_id=batch,source_system="mongo",source_schema=None,
                                   source_pk=str(document["_id"]),extracted_at=extracted,
                                   payload=json_util.dumps(document,json_options=json_util.CANONICAL_JSON_OPTIONS))
                        for key,typ,nullable in fields:
                            value = document.get(key)
                            if value is None:
                                if not nullable:
                                    raise ValueError(f"{collection}/{document['_id']}: missing {key}")
                            elif key == "_id":
                                value = str(value)
                            elif typ == "time":
                                value = parse_time(value)
                            elif typ == "date":
                                value = parse_time(value).date() if not isinstance(value,date) or isinstance(value,datetime) else value
                            elif typ == "money":
                                value = decimal(value)
                            elif isinstance(value,(dict,list)):
                                value = json_util.dumps(value,json_options=json_util.CANONICAL_JSON_OPTIONS)
                            row[key] = value
                        rows.append(row)
                        if len(rows) == CHUNK:
                            yield rows
                            rows = []
                    if rows:
                        yield rows
            count,snapshot = write_snapshot(cat,name,batch,chunks())
            completed.append((name,count,snapshot,extracted))
    for name,count,snapshot,extracted in completed:
        record_dataset(batch,"stg."+name,count,snapshot,extracted)
    return {"batch_id":batch,"datasets":len(completed)}
