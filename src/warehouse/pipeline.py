import hashlib
import json
import tempfile
from pathlib import Path
from uuid import UUID

from . import connections, control, extract
from .contracts import CDM, DDS, STG, arrow_schema, sql_type
from .settings import ROOT, setting

SORT_KEYS = {
    "craft_customer_monthly":("client_id","report_period"),
    "restaurant_daily_sales":("report_date","restaurant_id"),
    "external_client_activity_daily":("report_date","client_id"),
    "marketing_daily_sales":("report_date",),
    "external_order_statuses_daily":("report_date","client_id"),
}


class RowHash:
    def __init__(self):
        self.count = 0
        self.hash = hashlib.sha256()

    def add(self, rows):
        for row in rows:
            if self.count:
                self.hash.update(b"\n")
            self.hash.update(json.dumps(control.canonical(row),ensure_ascii=False,sort_keys=True,
                                        separators=(",",":")).encode())
            self.count += 1

    def digest(self):
        return self.hash.hexdigest()


def check_dependencies(run_id):
    with connections.postgres() as conn:
        conn.execute("SELECT 1")
    with connections.mongo() as client:
        client.admin.command("ping")
    connections.s3().head_bucket(Bucket=setting("S3_BUCKET"))
    connections.catalog().list_namespaces()
    connections.query("SELECT 1")
    with connections.clickhouse(reader=True) as client:
        client.query("SELECT 1")
    return control.start_batch(run_id)


def reject_rows(sql, message):
    rows = connections.query(sql + " LIMIT 10")
    if rows:
        raise ValueError(f"{message}; sample keys: {rows}")


def validate_stg(batch):
    UUID(batch)
    loaded = control.require_datasets(batch,["stg."+name for name in STG])
    for name in STG:
        predicate = "TRUE" if name == "pg_logs" else f"batch_id='{batch}'"
        n = connections.query(f"SELECT count(*) FROM lake.stg.{name} WHERE {predicate}")[0][0]
        if n != loaded["stg."+name][0]:
            raise ValueError(f"STG row count mismatch: {name}")
        key = "log_id" if name == "pg_logs" else "source_pk"
        reject_rows(f"SELECT {key} FROM lake.stg.{name} WHERE {predicate} GROUP BY {key} HAVING count(*)<>1",
                    f"Duplicate STG key in {name}")
    reject_rows(f"SELECT order_id FROM lake.stg.pg_public_order WHERE batch_id='{batch}' AND "
                "(order_price IS NULL OR order_price<0 OR status NOT IN "
                "('created','in_progress','in progress','delivery','done','cancelled') OR "
                "(status='done' AND (delivery_date IS NULL OR delivery_date<order_date)) OR "
                "(status<>'done' AND delivery_date IS NOT NULL))", "Invalid craft order/unknown historical price")
    reject_rows(f"SELECT order_id FROM lake.stg.mongo_orders WHERE batch_id='{batch}' AND "
                "(update_time<order_date OR cost<0 OR payment<0 OR final_status='')", "Invalid restaurant order")
    reject_rows(f"SELECT id FROM lake.stg.pg_external_marketing_research WHERE batch_id='{batch}' AND "
                "(length(CAST(date_id AS VARCHAR))<>8 OR try(date_parse(CAST(date_id AS VARCHAR),'%Y%m%d')) IS NULL)",
                "date_id must be a valid YYYYMMDD date")


def build_group(batch, prefix):
    UUID(batch)
    names = [name for name in DDS if name.startswith(prefix)]
    control.clear_datasets(batch,["dds."+name for name in names])
    cat = connections.catalog()
    for name in names:
        query = (ROOT / "sql/dds" / (name+".sql")).read_text().replace("{{batch_id}}",batch).strip().rstrip(";")
        casts = ", ".join(f'CAST("{n}" AS {sql_type(t)}) AS "{n}"' for n,t,_ in DDS[name])
        connections.query(f"CREATE OR REPLACE TABLE lake.dds.{name} "
                          f"WITH (format='PARQUET', format_version=2) AS SELECT {casts} FROM ({query}) source")
        table = cat.load_table(("dds",name))
        count = connections.query(f"SELECT count(*) FROM lake.dds.{name}")[0][0]
        control.record_dataset(batch,"dds."+name,count,table.current_snapshot().snapshot_id)


def validate_dds(batch):
    loaded = control.require_datasets(batch,["dds."+name for name in DDS])
    for name,fields in DDS.items():
        key = fields[0][0]
        reject_rows(f'SELECT "{key}" FROM lake.dds.{name} GROUP BY "{key}" HAVING count(*)<>1',
                    f"Duplicate DDS key in {name}")
        required = " OR ".join(f'"{n}" IS NULL' for n,_,nullable in fields if not nullable)
        reject_rows(f'SELECT "{key}" FROM lake.dds.{name} WHERE {required}',f"Required DDS field missing in {name}")
        actual = connections.query(f"SELECT count(*) FROM lake.dds.{name}")[0][0]
        if actual != loaded["dds."+name][0]:
            raise ValueError(f"DDS row count changed outside batch: {name}")
    relations = {
        "fact_craft_orders": {"client_key":("dim_craft_client","client_key"),"master_key":("dim_craft_master","master_key"),
            "product_key":("dim_craft_product","product_key"),"status_code":("dim_craft_order_status","status_code"),
            "created_date_key":("dim_date","date_key"),"delivery_date_key":("dim_date","date_key")},
        "fact_craft_offers":{"master_key":("dim_craft_master","master_key"),"product_key":("dim_craft_product","product_key")},
        "fact_restaurant_orders":{"client_key":("dim_restaurant_client","client_key"),"restaurant_key":("dim_restaurant","restaurant_key"),
            "status_code":("dim_restaurant_order_status","status_code"),"date_key":("dim_date","date_key")},
        "fact_external_order_statuses":{"client_key":("dim_external_client","client_key"),"date_key":("dim_date","date_key")},
        "fact_external_user_behavior":{"client_key":("dim_external_client","client_key"),"date_key":("dim_date","date_key")},
        "fact_external_marketing_research":{"date_key":("dim_date","date_key")},
    }
    for fact,fields in relations.items():
        for key,(dimension,dimkey) in fields.items():
            reject_rows(f"SELECT f.{key} FROM lake.dds.{fact} f LEFT JOIN lake.dds.{dimension} d "
                        f"ON f.{key}=d.{dimkey} WHERE f.{key} IS NOT NULL AND d.{dimkey} IS NULL",
                        f"Orphan key {fact}.{key}")
    reject_rows("SELECT master_key,product_key FROM lake.dds.fact_craft_offers "
                "GROUP BY master_key,product_key HAVING count(*)<>1", "Duplicate offer pair")
    reject_rows("SELECT o.order_id FROM lake.dds.fact_craft_orders o LEFT JOIN lake.dds.fact_craft_offers f "
                "ON o.master_key=f.master_key AND o.product_key=f.product_key WHERE f.id IS NULL", "Unknown craft offer")


def publish(batch, fail_before_publish=False):
    import pyarrow as pa
    import pyarrow.parquet as pq
    control.require_datasets(batch,["dds."+name for name in DDS])
    prepared = []
    with tempfile.TemporaryDirectory(prefix="warehouse-cdm-") as folder:
        for name,fields in CDM.items():
            schema = arrow_schema(fields)
            path = Path(folder)/(name+".parquet")
            checksum = RowHash()
            previous_key = None
            with connections.trino() as conn, pq.ParquetWriter(path,schema,compression="snappy") as writer:
                cursor = conn.cursor()
                cursor.execute((ROOT/"sql/cdm"/(name+".sql")).read_text())
                names = [column[0] for column in cursor.description]
                if names != schema.names:
                    raise ValueError(f"Unexpected CDM columns for {name}: {names}")
                while records := cursor.fetchmany(1000):
                    table = pa.Table.from_pylist([dict(zip(names,row)) for row in records],schema=schema)
                    table.validate(full=True)
                    for field in schema:
                        if not field.nullable and table[field.name].null_count:
                            raise ValueError(f"NULL in required CDM column {name}.{field.name}")
                    rows = table.to_pylist()
                    for row in rows:
                        key = tuple(row[col] for col in SORT_KEYS[name])
                        if key == previous_key:
                            raise ValueError(f"Duplicate mart key: {name} {key}")
                        previous_key = key
                    checksum.add(rows)
                    writer.write_table(table,row_group_size=1000)
            if pq.ParquetFile(path).metadata.num_rows != checksum.count:
                raise ValueError(f"Incomplete Parquet: {name}")
            prepared.append((name,path,checksum))
        if fail_before_publish:
            raise RuntimeError("Injected failure after preparation, before any publication")
        client = connections.s3()
        for name,path,checksum in prepared:
            with connections.postgres("control") as conn:
                conn.execute("INSERT INTO publications(batch_id,mart,status,row_count,content_sha256) VALUES(%s,%s,'prepared',%s,%s) "
                             "ON CONFLICT(batch_id,mart) DO UPDATE SET status='prepared',row_count=excluded.row_count,"
                             "content_sha256=excluded.content_sha256,object_etag=NULL,published_at=NULL",
                             (batch,name,checksum.count,checksum.digest()))
            key = f"cdm/{name}/current.parquet"
            client.upload_file(str(path),setting("S3_BUCKET"),key,
                               ExtraArgs={"Metadata":{"batch-id":batch,"rows-sha256":checksum.digest()}})
            etag = client.head_object(Bucket=setting("S3_BUCKET"),Key=key)["ETag"]
            with connections.postgres("control") as conn:
                conn.execute("UPDATE publications SET status='published',object_etag=%s,published_at=clock_timestamp() "
                             "WHERE batch_id=%s AND mart=%s",(etag,batch,name))


def verify_clickhouse(batch):
    import pyarrow as pa
    with connections.postgres("control") as conn:
        expected = {row[0]:row[1:] for row in conn.execute(
            "SELECT mart,row_count,content_sha256,status FROM publications WHERE batch_id=%s",(batch,))}
    with connections.clickhouse(reader=True) as client:
        for name,fields in CDM.items():
            if name not in expected or expected[name][2] not in ("published","verified"):
                raise ValueError(f"Mart not published in batch {batch}: {name}")
            checksum = RowHash()
            names = [f[0] for f in fields]
            query = f"SELECT {','.join(names)} FROM cdm.{name} ORDER BY {','.join(SORT_KEYS[name])}"
            with client.query_row_block_stream(query,settings={"use_query_cache":0}) as stream:
                for block in stream:
                    rows = pa.Table.from_pylist([dict(zip(names,row)) for row in block],schema=arrow_schema(fields)).to_pylist()
                    checksum.add(rows)
            if (checksum.count,checksum.digest()) != expected[name][:2]:
                raise ValueError(f"ClickHouse content mismatch: {name} ({checksum.count} rows)")
            with connections.postgres("control") as conn:
                conn.execute("UPDATE publications SET status='verified' WHERE batch_id=%s AND mart=%s",(batch,name))


def mark_success(batch):
    with connections.postgres("control") as conn:
        count = conn.execute("SELECT count(*) FROM publications WHERE batch_id=%s AND status='verified'",(batch,)).fetchone()[0]
        if count != len(CDM):
            raise ValueError("Cannot mark batch successful before all five marts are verified")
        conn.execute("UPDATE batches SET status='success',error=NULL,finished_at=clock_timestamp() WHERE batch_id=%s",(batch,))


STEPS = {
    "extract_postgres_snapshot_and_logs":extract.postgres_snapshot,
    "extract_mongo_snapshot":extract.mongo_snapshot,
    "validate_stg":validate_stg,
    "build_dimensions":lambda batch:build_group(batch,"dim_"),
    "build_facts":lambda batch:build_group(batch,"fact_"),
    "validate_dds":validate_dds,
    "calculate_and_publish_cdm":publish,
    "verify_clickhouse":verify_clickhouse,
    "mark_batch_success":mark_success,
}


def execute_step(name,batch):
    try:
        result = STEPS[name](batch)
        print(f"{name}: completed, batch={batch}",flush=True)
        return result
    except Exception as exc:
        control.fail_batch(batch,exc)
        raise


def run(run_id):
    batch = check_dependencies(run_id)
    for name in STEPS:
        execute_step(name,batch)
    return batch
