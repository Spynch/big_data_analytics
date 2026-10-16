from .settings import pg_params, setting


def postgres(target="source", admin=False, **kwargs):
    import psycopg
    return psycopg.connect(**pg_params(target, admin), **kwargs)


def mongo(admin=False):
    from pymongo import MongoClient
    return MongoClient("mongo-source", 27017,
                       username=setting("MONGO_ADMIN" if admin else "MONGO_ETL_USER"),
                       password=setting("MONGO_PASSWORD" if admin else "MONGO_ETL_PASSWORD"),
                       authSource="admin", tz_aware=True, serverSelectionTimeoutMS=10000)


def s3():
    import boto3
    from botocore.config import Config
    return boto3.client("s3", endpoint_url=setting("S3_ENDPOINT"),
                        region_name=setting("S3_REGION"),
                        aws_access_key_id=setting("S3_ETL_USER"),
                        aws_secret_access_key=setting("S3_ETL_PASSWORD"),
                        config=Config(s3={"addressing_style": "path"},
                                      retries={"max_attempts": 4, "mode": "standard"}))


def catalog():
    from pyiceberg.catalog import load_catalog
    return load_catalog("lake", type="rest", uri="http://lakekeeper:8181/catalog",
                        warehouse="warehouse", **{
                            "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
                            "s3.endpoint": setting("S3_ENDPOINT"),
                            "s3.region": setting("S3_REGION"),
                            "s3.access-key-id": setting("S3_ETL_USER"),
                            "s3.secret-access-key": setting("S3_ETL_PASSWORD"),
                            "s3.force-virtual-addressing": "false",
                            "header.X-Iceberg-Access-Delegation": "client-managed",
                        })


def trino():
    from trino.dbapi import connect
    return connect(host="trino", port=8080, user="warehouse_etl", catalog="lake",
                   timezone=setting("REPORT_TIMEZONE", "UTC"), request_timeout=120,
                   session_properties={"query_max_run_time": "10m"})


def clickhouse(reader=False):
    import clickhouse_connect
    return clickhouse_connect.get_client(host="clickhouse", port=8123,
        username=setting("CLICKHOUSE_READ_USER" if reader else "CLICKHOUSE_USER"),
        password=setting("CLICKHOUSE_READ_PASSWORD" if reader else "CLICKHOUSE_PASSWORD"))


def query(sql, params=None):
    with trino() as connection:
        cur = connection.cursor()
        cur.execute(sql, params or [])
        return cur.fetchall()
