"""Mutation tests for the demo only. Restore changed source rows in finally blocks."""
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from warehouse import bootstrap, connections as db, control, extract, migrate, pipeline, seed
from warehouse.cli import trigger
from warehouse.contracts import PG
from warehouse.settings import setting
from .helpers import all_marts, assert_golden, etags, golden, mart


def run_id(prefix):
    return f'acceptance__{prefix}__{uuid4()}'


def test_audit_dml_copy_truncate_and_rollback():
    with db.postgres(admin=True,autocommit=True) as conn:
        original = conn.execute('SELECT count(*) FROM public.logs').fetchone()[0]
        conn.execute('BEGIN')
        try:
            start = conn.execute('SELECT coalesce(max(id),0) FROM public.logs').fetchone()[0]
            conn.execute("INSERT INTO public.client(client_id,name) VALUES(900001,'audit A'),(900002,'audit B')")
            conn.execute("UPDATE public.client SET name=name || ' updated' WHERE client_id IN (900001,900002)")
            conn.execute('DELETE FROM public.client WHERE client_id=900001')
            with conn.cursor().copy('COPY external_source.user_behavior(id,date_time,client_id) FROM STDIN') as copy:
                copy.write_row((900001,'2026-01-01T00:00:00Z',900001))
                copy.write_row((900002,'2026-01-02T00:00:00Z',900002))
            conn.execute('UPDATE external_source.user_behavior SET client_id=900003 WHERE id IN (900001,900002)')
            conn.execute('DELETE FROM external_source.user_behavior WHERE id=900002')
            logs = conn.execute('SELECT object_schema,object_type,operation,object_value FROM public.logs WHERE id>%s ORDER BY id',(start,)).fetchall()
            assert [r[2] for r in logs] == ['INSERT','INSERT','UPDATE','UPDATE','DELETE','INSERT','INSERT','UPDATE','UPDATE','DELETE']
            assert logs[4][3]['name'] == 'audit A updated'  # DELETE stores OLD.
            assert logs[2][3]['email'] is None and logs[7][3]['client_id'] == 900003
            assert {r[0] for r in logs} == {'public','external_source'}
            before = {f'{s}.{t}':conn.execute(f'SELECT count(*) FROM "{s}"."{t}"').fetchone()[0]
                      for s,t,_,_ in PG.values() if t!='logs'}
            checkpoint = conn.execute('SELECT max(id) FROM public.logs').fetchone()[0]
            conn.execute('TRUNCATE public."order",public.master_product,public.master,public.product,public.client, '
                         'external_source.order_statuses,external_source.user_behavior,external_source.marketing_research')
            captured = conn.execute("SELECT object_schema || '.' || object_type,count(*) FROM public.logs "
                                    "WHERE id>%s AND operation='TRUNCATE' GROUP BY 1",(checkpoint,)).fetchall()
            assert dict(captured) == {k:v for k,v in before.items() if v}
        finally:
            conn.execute('ROLLBACK')
        assert conn.execute('SELECT count(*) FROM public.logs').fetchone()[0] == original
        assert conn.execute('SELECT count(*) FROM public."order"').fetchone()[0] == 11


def test_rejected_source_values_and_csv_contract(tmp_path,monkeypatch):
    for delivery in (None,'2025-12-31T00:00:00Z'):
        with pytest.raises(psycopg.errors.CheckViolation):
            with db.postgres(admin=True) as conn:
                conn.execute('UPDATE public."order" SET delivery_date=%s WHERE order_id=1',(delivery,))
    with db.postgres(admin=True) as conn:
        conn.execute('INSERT INTO public."order"(order_id,master_id,product_id,client_id,order_date,status) '
                     "VALUES(900001,1,1,1,'2026-04-01','created')")
        assert conn.execute('SELECT order_price FROM public."order" WHERE order_id=900001').fetchone()[0] == Decimal('100.00')
        conn.rollback()
    csv = tmp_path/'marketing_research.csv'
    csv.write_text('date_id,sales_qty,sales_amt,category_id\n20260115,2,100.00,10\n20260115,2,100.00,10\n')
    first = list(seed.external_rows(tmp_path,'marketing_research'))
    assert len(first) == len({r['id'] for r in first}) == 2
    assert first == list(seed.external_rows(tmp_path,'marketing_research'))
    csv.write_text('date_id,sales_qty,sales_amt,category_id\n20260230,2,100.00,10\n')
    with pytest.raises(ValueError,match='line 2'):
        list(seed.external_rows(tmp_path,'marketing_research'))
    monkeypatch.setenv('SOURCE_TIMEZONE','Europe/Berlin')
    with pytest.raises(ValueError,match='Ambiguous or nonexistent'):
        extract.parse_time('2026-10-25T02:30:00')


def test_seed_and_migrations_repeat_without_loss():
    with db.postgres() as conn:
        before = conn.execute('SELECT count(*) FROM public.logs').fetchone()[0]
    with db.mongo() as client:
        mongo_before = {n:list(client[setting('MONGO_DB')][n].find().sort('_id',1)) for n in ['clients','orders','restaurant']}
    objects = etags()
    seed.run()
    seed.run()
    for target in ['postgres','control','lake','clickhouse']:
        migrate.run(target)
    bootstrap.lakekeeper()
    bootstrap.empty_cdm()
    with db.postgres() as conn:
        assert conn.execute('SELECT count(*) FROM public.logs').fetchone()[0] == before
    with db.mongo() as client:
        assert mongo_before == {n:list(client[setting('MONGO_DB')][n].find().sort('_id',1)) for n in mongo_before}
    assert etags() == objects
    assert_golden()


def test_airflow_repeat_mutations_publication_failure_and_retry():
    before = all_marts()
    trigger(run_id('airflow_first'))
    assert all_marts() == before
    trigger(run_id('airflow_repeat'))
    assert all_marts() == before
    attempt = run_id('same_batch_retry')
    try:
        with db.postgres(admin=True) as conn:
            conn.execute('UPDATE public."order" SET paid_at=order_date WHERE order_id=3')
            conn.execute('UPDATE public.master_product SET price=999.00 WHERE id=1')
            conn.execute('DELETE FROM public."order" WHERE order_id=11')
        batch = pipeline.run(attempt)
        changed = mart('craft_customer_monthly')
        expected = golden()
        for row in expected:
            if row['client_id'] == 1: row['paid_orders_amount_all_time'] = '880.00'
            if row['client_id'] == 2:
                row['created_orders_count_month'] = row['unfinished_orders_count_month'] = 2
        assert changed == expected
        assert db.query('SELECT count(*) FROM lake.dds.fact_craft_orders')[0][0] == 10
        assert db.query('SELECT order_price FROM lake.dds.fact_craft_orders WHERE order_id=1')[0][0] == Decimal('100.00')
        assert pipeline.run(attempt) == batch
        assert mart('craft_customer_monthly') == expected
        assert db.query(f"SELECT count(*) FROM lake.stg.pg_public_order WHERE batch_id='{batch}'")[0][0] == 10
        # All files must survive a failure while preparing the next publication.
        old_objects,old_reports = etags(),all_marts()
        with pytest.raises(RuntimeError,match='Injected failure'):
            pipeline.publish(batch,fail_before_publish=True)
        assert etags() == old_objects and all_marts() == old_reports
        pipeline.publish(batch)
        pipeline.verify_clickhouse(batch)
        # Bad legacy snapshots fail explicitly, without publishing partial output.
        for assignment in ['order_price=NULL','delivery_date=NULL',"delivery_date=TIMESTAMP '2025-01-01 00:00:00 UTC'"]:
            try:
                db.query(f"UPDATE lake.stg.pg_public_order SET {assignment} WHERE batch_id='{batch}' AND order_id=1")
                with pytest.raises(ValueError,match='Invalid craft order'):
                    pipeline.validate_stg(batch)
                assert etags() == old_objects
            finally:
                extract.postgres_snapshot(batch)
    finally:
        seed.run()
        pipeline.run(run_id('restore'))
    assert_golden()


def test_audit_out_of_order_commits_and_full_reread():
    batch = control.start_batch(run_id('commit_order'))
    first,second = db.postgres(admin=True),db.postgres(admin=True)
    try:
        first.execute("INSERT INTO external_source.user_behavior VALUES(910001,'2026-01-01',910001)")
        low = first.execute("SELECT max(id) FROM public.logs WHERE object_type='user_behavior'").fetchone()[0]
        second.execute("INSERT INTO external_source.user_behavior VALUES(910002,'2026-01-01',910002)")
        high = second.execute("SELECT max(id) FROM public.logs WHERE object_type='user_behavior'").fetchone()[0]
        second.commit()
        assert low < high
        extract.postgres_snapshot(batch)
        assert db.query(f'SELECT count(*) FROM lake.stg.pg_logs WHERE log_id={low}')[0][0] == 0
        first.commit()
        extract.postgres_snapshot(batch)
        assert db.query(f'SELECT count(*),count(DISTINCT log_id) FROM lake.stg.pg_logs WHERE log_id IN ({low},{high})')[0] == [2,2]
    finally:
        first.rollback()
        second.rollback()
        first.close()
        second.close()
        with db.postgres(admin=True) as conn:
            conn.execute('DELETE FROM external_source.user_behavior WHERE id IN (910001,910002)')
        control.fail_batch(batch,'Extraction-only acceptance probe; no publication intended')
        pipeline.run(run_id('restore_commit_order'))
