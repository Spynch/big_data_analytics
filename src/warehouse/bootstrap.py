import io
import json
import subprocess
from pathlib import Path

from psycopg import sql

from .connections import postgres, mongo, s3
from .settings import setting


def role(conn, name, password):
    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (name,)).fetchone():
        conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(name), sql.Literal(password)))


def meta():
    with postgres("meta", autocommit=True) as conn:
        for name, env in [("airflow","AIRFLOW_DB_PASSWORD"),("iceberg_catalog","CATALOG_DB_PASSWORD"),
                          ("warehouse_control","CONTROL_DB_PASSWORD")]:
            role(conn, name, setting(env))
            if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(name), sql.Identifier(name)))
            conn.execute(sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name)))
            conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(name),sql.Identifier(name)))
    with postgres(admin=True) as conn:
        role(conn, setting("SOURCE_ETL_USER"), setting("SOURCE_ETL_PASSWORD"))
    with mongo(admin=True) as client:
        user = setting("MONGO_ETL_USER")
        if not client.admin.command("usersInfo", user)["users"]:
            client.admin.command("createUser", user, pwd=setting("MONGO_ETL_PASSWORD"),
                                 roles=[{"role":"read", "db":setting("MONGO_DB")}])
    print("Service databases and source readers are ready")


def source_grants():
    with postgres(admin=True) as conn:
        reader = sql.Identifier(setting("SOURCE_ETL_USER"))
        for schema in ["public", "external_source"]:
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema),reader))
            conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(sql.Identifier(schema),reader))
            conn.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO {}").format(sql.Identifier(schema),reader))


def lakekeeper():
    import requests
    base = "http://lakekeeper:8181/management/v1"
    def request(method, path, payload=None, allowed=()):
        r = requests.request(method, base + path, json=payload, timeout=30)
        if r.status_code not in allowed:
            r.raise_for_status()
        return r
    response = request("POST", "/bootstrap", {"accept-terms-of-use":True}, allowed=(400,409))
    if response.status_code == 400 and response.json().get("error",{}).get("type") != "CatalogAlreadyBootstrapped":
        response.raise_for_status()
    project = "00000000-0000-0000-0000-000000000000"
    response = request("GET", f"/warehouse?project-id={project}").json()
    warehouses = response.get("warehouses", [])
    existing = next((w for w in warehouses if w["name"] == "warehouse"), None)
    if not existing:
        request("POST", "/warehouse", {
            "warehouse-name":"warehouse", "project-id":project,
            "storage-profile": {"type":"s3", "bucket":setting("S3_BUCKET"),
                "region":setting("S3_REGION"), "endpoint":setting("S3_ENDPOINT"),
                "path-style-access":True, "flavor":"minio", "sts-enabled":False},
            "storage-credential":{"type":"s3", "credential-type":"access-key",
                "aws-access-key-id":setting("S3_ETL_USER"), "aws-secret-access-key":setting("S3_ETL_PASSWORD")},
        })
    from .connections import catalog
    cat = catalog()
    for name in ["stg", "dds"]:
        location = f"s3://{setting('S3_BUCKET')}/{name}/"
        if (name,) not in cat.list_namespaces():
            cat.create_namespace(name, properties={"location":location})
        actual = cat.load_namespace_properties(name).get("location", "")
        if actual.rstrip("/") != location.rstrip("/"):
            raise ValueError(f"Namespace {name} has unexpected location: {actual}")
    print("Lakekeeper warehouse, namespaces and object storage validated")


def empty_cdm():
    import pyarrow as pa
    import pyarrow.parquet as pq
    from botocore.exceptions import ClientError
    from .contracts import CDM, arrow_schema
    client = s3()
    for name, definition in CDM.items():
        key = f"cdm/{name}/current.parquet"
        try:
            client.head_object(Bucket=setting("S3_BUCKET"),Key=key)
            continue
        except ClientError as exc:
            if exc.response["ResponseMetadata"]["HTTPStatusCode"] != 404:
                raise
        out = io.BytesIO()
        pq.write_table(pa.Table.from_batches([], schema=arrow_schema(definition)),out,compression="snappy")
        client.put_object(Bucket=setting("S3_BUCKET"),Key=key,Body=out.getvalue(),IfNoneMatch="*")
    print("Only absent CDM files initialized")


def airflow():
    subprocess.run(["airflow", "db", "migrate"], check=True)
    passwords = Path("/opt/airflow/logs/simple_auth_passwords.json")
    if not passwords.exists():
        passwords.write_text(json.dumps({setting("AIRFLOW_ADMIN"):setting("AIRFLOW_ADMIN_PASSWORD")}))
        passwords.chmod(0o600)
    from airflow.models.connection import Connection
    from airflow.utils.session import create_session
    entries = [
        Connection(conn_id="warehouse_postgres",conn_type="postgres",host="postgres-source",port=5432,
                   login=setting("SOURCE_ETL_USER"),password=setting("SOURCE_ETL_PASSWORD"),schema=setting("SOURCE_DB")),
        Connection(conn_id="warehouse_trino",conn_type="trino",host="trino",port=8080,login="warehouse_etl"),
        Connection(conn_id="warehouse_minio",conn_type="aws",login=setting("S3_ETL_USER"),password=setting("S3_ETL_PASSWORD"),
                   extra=json.dumps({"endpoint_url":setting("S3_ENDPOINT"),"region_name":setting("S3_REGION")})),
        Connection(conn_id="warehouse_mongo",conn_type="mongo",host="mongo-source",port=27017,
                   login=setting("MONGO_ETL_USER"),password=setting("MONGO_ETL_PASSWORD"),schema=setting("MONGO_DB")),
        Connection(conn_id="warehouse_clickhouse",conn_type="generic",host="clickhouse",port=8123,
                   login=setting("CLICKHOUSE_READ_USER"),password=setting("CLICKHOUSE_READ_PASSWORD")),
    ]
    with create_session() as session:
        for entry in entries:
            if not session.query(Connection).filter_by(conn_id=entry.conn_id).first():
                session.add(entry)
    print("Airflow initialized; connections contain no source write credentials")
