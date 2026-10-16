"""Read-only checks of the running seeded stack. No implicit seeding or DAG trigger."""
import io
import json

import pyarrow.parquet as pq

from warehouse import connections as db
from warehouse.contracts import CDM, DDS, STG, arrow_schema
from warehouse.settings import setting
from .helpers import assert_golden, mart


def test_all_17_fields_postgres_trino_clickhouse():
    assert_golden()


def test_other_marts_and_no_join_multiplication():
    assert mart('external_client_activity_daily') == [
        dict(report_date='2026-01-15',client_id=1,behavior_events_count=3,quantity_total=5,payment_amount_total='300.00'),
        dict(report_date='2026-01-16',client_id=2,behavior_events_count=0,quantity_total=1,payment_amount_total='90.00'),
        dict(report_date='2026-01-17',client_id=2,behavior_events_count=1,quantity_total=0,payment_amount_total='0.00')]
    assert mart('external_order_statuses_daily') == [
        dict(report_date='2026-01-15',client_id=1,quantity_total=5,payment_amount_total='300.00'),
        dict(report_date='2026-01-16',client_id=2,quantity_total=1,payment_amount_total='90.00')]
    assert mart('marketing_daily_sales') == [
        dict(report_date='2026-01-15',sales_qty=7,sales_amt='700.00'),
        dict(report_date='2026-01-16',sales_qty=1,sales_amt='90.00')]
    assert mart('restaurant_daily_sales') == [
        dict(report_date='2026-01-15',restaurant_id=1,restaurant_name='Кафе Сад',orders_count=2,
             cost_total='800.00',payment_total='750.00',bonus_for_visit_total='30.00')]
    assert db.query('SELECT count(*) FROM lake.dds.fact_craft_orders')[0][0] == 11
    keys = [db.query(f'SELECT client_key FROM lake.dds.{table} WHERE client_id=1')[0][0]
            for table in ['dim_craft_client','dim_restaurant_client','dim_external_client']]
    assert len(set(keys)) == 3


def test_physical_storage_schemas_and_audit():
    cat = db.catalog()
    assert {name for _,name in cat.list_tables('stg')} == set(STG)
    assert {name for _,name in cat.list_tables('dds')} == set(DDS)
    for namespace,definitions in [('stg',STG),('dds',DDS)]:
        for name in definitions:
            table = cat.load_table((namespace,name))
            assert table.metadata.format_version == 2
            assert table.location().startswith(f"s3://{setting('S3_BUCKET')}/{namespace}/")
            assert table.current_snapshot() is not None
    with db.clickhouse() as client:
        assert sorted(client.query("SELECT name,engine FROM system.tables WHERE database='cdm'").result_rows) == sorted(
            (name,'S3') for name in CDM)
        for name,definition in CDM.items():
            actual = client.query(f'DESCRIBE TABLE cdm.{name}').result_rows
            assert [row[0] for row in actual] == [f[0] for f in definition]
    s3 = db.s3()
    for name,definition in CDM.items():
        body = s3.get_object(Bucket=setting('S3_BUCKET'),Key=f'cdm/{name}/current.parquet')['Body'].read()
        assert body[:4] == body[-4:] == b'PAR1'
        assert pq.read_schema(io.BytesIO(body)).equals(arrow_schema(definition))
    count,unique = db.query('SELECT count(*),count(DISTINCT log_id) FROM lake.stg.pg_logs')[0]
    assert count == unique > 0
    with db.postgres() as conn:
        assert conn.execute("SELECT count(*) FROM public.logs WHERE object_schema NOT IN ('public','external_source')").fetchone()[0] == 0
    payload = db.query('SELECT payload FROM lake.stg.mongo_orders LIMIT 1')[0][0]
    document = json.loads(payload)
    assert '$oid' in document['_id'] and '$date' in document['order_date']
    assert '$numberDecimal' in document['cost'] and len(document['ordered_dish']) == 2


def test_successful_batch_is_fully_verified():
    with db.postgres('control') as conn:
        batch = conn.execute("SELECT batch_id FROM batches WHERE status='success' ORDER BY finished_at DESC LIMIT 1").fetchone()
        assert batch is not None
        assert conn.execute("SELECT count(*) FROM publications WHERE batch_id=%s AND status='verified'",batch).fetchone()[0] == 5
        assert conn.execute("SELECT count(*) FROM dataset_loads WHERE batch_id=%s",batch).fetchone()[0] == 27
        assert conn.execute("SELECT count(*) FROM lake_migrations WHERE status<>'success'").fetchone()[0] == 0
