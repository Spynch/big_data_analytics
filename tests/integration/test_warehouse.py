import hashlib
import os
import shutil
import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg
from bson import ObjectId
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from warehouse.config import ROOT, Settings
from warehouse.csv_import import import_csvs
from warehouse.migrate import migrate
from airflow_utils.mongo_source import mongo_client
from airflow_utils.refresh import WRITER_LOCK, refresh_warehouse
from warehouse.seed import seed


class WarehouseIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv('WAREHOUSE_TEST_MODE') != '1':
            raise RuntimeError('Run with WAREHOUSE_TEST_MODE=1 in a separate Compose project')
        cls.settings = Settings.from_env()
        migrate(cls.settings)
        seed(cls.settings)
        refresh_warehouse(cls.settings)

    def tearDown(self):
        seed(self.settings)
        refresh_warehouse(self.settings)

    def pg(self, target='warehouse', role='etl', **kwargs):
        return psycopg.connect(self.settings.dsn(target, role), **kwargs)

    def scalar(self, query, params=None, target='warehouse'):
        with self.pg(target) as connection:
            return connection.execute(query, params).fetchone()[0]

    def monthly(self, client, period):
        with self.pg(row_factory=dict_row) as connection:
            return connection.execute('SELECT * FROM cdm.craft_customer_monthly WHERE client_id=%s AND report_period=%s',
                                      (client, period)).fetchone()

    def snapshot(self, include_extracted=True):
        with self.pg() as connection:
            tables = connection.execute('''
                SELECT n.nspname, c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname IN ('stg', 'dds', 'cdm') AND relkind IN ('r','v') ORDER BY 1,2
            ''').fetchall()
            result = {}
            for schema, table in tables:
                expression = "to_jsonb(t)" if include_extracted else "to_jsonb(t) - 'extracted_at'"
                query = sql.SQL(f'SELECT {expression} FROM {{}} t ORDER BY {expression}::text').format(sql.Identifier(schema, table))
                result[f'{schema}.{table}'] = connection.execute(query).fetchall()
            return result

    def test_bootstrap_and_seed_repeat_without_audit_noise(self):
        before = self.snapshot(False)
        count = self.scalar('SELECT count(*) FROM public.logs', target='source')
        migrate(self.settings)
        seed(self.settings)
        refresh_warehouse(self.settings)
        self.assertEqual(count, self.scalar('SELECT count(*) FROM public.logs', target='source'))
        self.assertEqual(before, self.snapshot(False))
        self.assertEqual(17, len(self.monthly(1, '2026-02')))
        with mongo_client(self.settings) as client:
            database = client[self.settings.get('MONGO_DB')]
            self.assertEqual({'clients', 'orders', 'restaurant'}, set(database.list_collection_names()))

    def test_monthly_cohorts_payment_and_medians(self):
        january = self.monthly(1, '2026-01')
        february = self.monthly(1, '2026-02')
        self.assertEqual((1, 1), (january['created_orders_count_month'], january['orders_count_month']))
        self.assertIsNone(january['avg_order_amount_month'])
        self.assertEqual((2, 2), (february['created_orders_count_month'], february['orders_count_month']))
        self.assertEqual(3, february['completed_orders_count_month'])
        self.assertEqual(Decimal('133.33'), february['avg_order_amount_month'])
        self.assertEqual(Decimal('1.0000'), february['median_completion_days_month'])
        self.assertEqual(Decimal('200.00'), february['paid_orders_amount_all_time'])
        self.assertEqual(january['paid_orders_amount_all_time'], february['paid_orders_amount_all_time'])
        tied = self.monthly(2, '2026-02')
        self.assertEqual(Decimal('2.0000'), tied['median_completion_days_month'])
        self.assertEqual('ceramics', tied['most_popular_category_month'])
        self.assertEqual(1, tied['most_popular_master_id_month'])
        self.assertEqual(Decimal('1.5000'), self.monthly(4, '2026-02')['median_completion_days_month'])
        self.assertIsNone(self.monthly(5, '2026-01'))
        self.assertEqual(1, self.monthly(5, '2026-02')['created_orders_count_month'])
        self.assertIsNone(self.monthly(6, '2026-02'))
        for row in (january, february, tied):
            self.assertEqual(row['orders_count_month'], row['created_orders_count_month'])
            expected = hashlib.md5(f"craft:{row['client_id']}:{row['report_period']}".encode()).hexdigest()
            self.assertEqual(expected, row['id'])

    def test_unfinished_paid_orders(self):
        january = self.monthly(3, '2026-01')
        february = self.monthly(3, '2026-02')
        self.assertEqual(1, january['in_progress_orders_count_month'])
        self.assertEqual(3, february['unfinished_orders_count_month'])
        for row in (january, february):
            self.assertEqual(0, row['completed_orders_count_month'])
            self.assertEqual(Decimal('300.00'), row['paid_orders_amount_all_time'])
            for field in ('avg_order_amount_month', 'median_completion_days_month',
                          'most_popular_category_month', 'most_popular_master_id_month'):
                self.assertIsNone(row[field])

    def test_external_facts_are_aggregated_before_join(self):
        with self.pg() as connection:
            rows = connection.execute('''
                SELECT report_date, client_id, quantity, payment_amount, behavior_events_count
                FROM cdm.external_client_activity_daily ORDER BY report_date, client_id
            ''').fetchall()
            self.assertEqual((date(2026, 2, 1), 1, 5, Decimal('50.30'), 2), rows[0])
            self.assertEqual((date(2026, 2, 2), 2, 0, Decimal('0'), 1), rows[1])
            self.assertEqual((date(2026, 2, 3), 2, 4, Decimal('40'), 0), rows[2])
            self.assertEqual((5, Decimal('300.30')), connection.execute(
                "SELECT sales_qty, sales_amt FROM cdm.marketing_daily_sales WHERE report_date='2026-02-01'").fetchone())
            self.assertEqual((2, Decimal('240.20'), Decimal('200.20'), Decimal('10.00')),
                             connection.execute('SELECT orders_count, cost_total, payment_total, bonus_for_visit_total FROM cdm.restaurant_daily_sales').fetchone())

    def test_client_domains_and_canonical_bson(self):
        self.assertEqual('Craft Client 1', self.scalar('SELECT name FROM dds.dim_craft_client WHERE client_id=1'))
        self.assertEqual('Restaurant Client 1', self.scalar('SELECT name FROM dds.dim_restaurant_client WHERE client_id=1'))
        self.assertEqual(1, self.scalar('SELECT client_id FROM dds.dim_external_client WHERE client_id=1'))
        payload = self.scalar("SELECT payload FROM stg.mongo_orders WHERE payload->'order_id'->>'$numberInt'='1'")
        self.assertEqual('120.10', payload['cost']['$numberDecimal'])
        self.assertIn('$numberLong', payload['order_date']['$date'])
        self.assertTrue(ObjectId.is_valid(payload['_id']['$oid']))
        self.assertEqual(2, len(payload['ordered_dish']))

    def test_audit_in_both_schemas_and_rollback(self):
        count = self.scalar('SELECT count(*) FROM public.logs', target='source')
        with self.pg('source', 'app') as connection:
            before = connection.execute('SELECT max(id) FROM public.logs').fetchone()[0]
            connection.execute("INSERT INTO public.master VALUES (-1, 'Test', NULL, NULL, NULL)")
            connection.execute("INSERT INTO public.product VALUES (-1, 'Test', NULL, 'test')")
            connection.execute('INSERT INTO public.master_product VALUES (-1, -1, -1, 42.12)')
            connection.execute("INSERT INTO public.client (client_id, name) VALUES (-1, 'Test')")
            connection.execute('''INSERT INTO public."order" (order_id,master_id,product_id,client_id,order_date,status)
                                  VALUES (-1,-1,-1,-1,now(),'created')''')
            connection.execute("INSERT INTO external_source.order_statuses VALUES (-1,now(),-1,1,42.12)")
            connection.execute("INSERT INTO external_source.user_behavior VALUES (-1,now(),-1)")
            connection.execute("INSERT INTO external_source.marketing_research VALUES (-1,20260201,1,42.12)")
            for table, column, value in (
                ('public.master', 'name', 'Updated'), ('public.product', 'name', 'Updated'),
                ('public.master_product', 'price', Decimal('99')), ('public.client', 'name', 'Updated'),
                ('public."order"', 'status', 'in_progress'), ('external_source.order_statuses', 'quantity', 2),
                ('external_source.user_behavior', 'client_id', -2), ('external_source.marketing_research', 'sales_qty', 2),
            ):
                key = {'public.master': 'master_id', 'public.product': 'product_id',
                       'public.client': 'client_id', 'public."order"': 'order_id'}.get(table, 'id')
                connection.execute(f'UPDATE {table} SET {column}=%s WHERE {key}=-1', (value,))
            for table, key in (
                ('public."order"', 'order_id'), ('public.master_product', 'id'), ('public.master', 'master_id'),
                ('public.product', 'product_id'), ('public.client', 'client_id'),
                ('external_source.order_statuses', 'id'), ('external_source.user_behavior', 'id'),
                ('external_source.marketing_research', 'id'),
            ):
                connection.execute(f'DELETE FROM {table} WHERE {key}=-1')
            events = connection.execute('SELECT object_schema,object_type,operation,object_value FROM public.logs WHERE id>%s ORDER BY id', (before,)).fetchall()
            self.assertEqual(24, len(events))
            self.assertEqual({'public', 'external_source'}, {row[0] for row in events})
            order_event = next(row[3] for row in events if row[1:3] == ('order', 'INSERT'))
            self.assertEqual(Decimal('42.12'), Decimal(str(order_event['order_price'])))
            self.assertIn('paid_at', order_event)
            self.assertIn('delivery_date', order_event)
            connection.rollback()
        self.assertEqual(count, self.scalar('SELECT count(*) FROM public.logs', target='source'))

    def test_copy_bulk_changes_and_truncate_are_audited(self):
        with self.pg('source', 'app') as connection:
            before = connection.execute('SELECT count(*) FROM public.logs').fetchone()[0]
            with connection.cursor().copy('COPY public.client (client_id,name) FROM STDIN') as copy:
                for key in range(-110, -100):
                    copy.write_row((key, 'Bulk'))
            connection.execute("UPDATE public.client SET address='Updated' WHERE client_id BETWEEN -110 AND -101")
            connection.execute('DELETE FROM public.client WHERE client_id BETWEEN -110 AND -101')
            self.assertEqual(30, connection.execute('SELECT count(*) FROM public.logs').fetchone()[0] - before)
            for table in ('public.client', 'external_source.user_behavior'):
                old_rows = connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                before = connection.execute('SELECT count(*) FROM public.logs').fetchone()[0]
                connection.execute(f'TRUNCATE {table}' + (' CASCADE' if table == 'public.client' else ''))
                self.assertGreaterEqual(connection.execute('SELECT count(*) FROM public.logs').fetchone()[0] - before, old_rows)
            self.assertGreater(connection.execute("SELECT count(*) FROM public.logs WHERE operation='TRUNCATE'").fetchone()[0], 0)
            connection.rollback()

    def test_offer_price_is_snapshot_and_no_fanout(self):
        count = self.scalar('SELECT count(*) FROM dds.fact_craft_orders')
        with self.pg('source', 'app') as connection:
            connection.execute('UPDATE public.master_product SET price=999 WHERE id=1')
        refresh_warehouse(self.settings)
        self.assertEqual(Decimal('100.00'), self.scalar('SELECT order_price FROM dds.fact_craft_orders WHERE order_id=1'))
        self.assertEqual(Decimal('999.00'), self.scalar('SELECT price FROM dds.fact_craft_offers WHERE id=1'))
        self.assertEqual(count, self.scalar('SELECT count(*) FROM dds.fact_craft_orders'))
        with self.pg('source', 'app') as connection:
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                connection.execute('''INSERT INTO public."order" (order_id,master_id,product_id,client_id,order_date,status)
                                      VALUES (-2,1,1,-999,now(),'created')''')
            connection.rollback()

    def test_updates_and_deletes_are_reflected(self):
        with self.pg('source', 'app') as connection:
            connection.execute("UPDATE public.client SET name='Changed' WHERE client_id=1")
            connection.execute('DELETE FROM public."order" WHERE order_id=2')
        with mongo_client(self.settings, admin=True) as client:
            client[self.settings.get('MONGO_DB')].orders.delete_one({'order_id': 2})
        refresh_warehouse(self.settings)
        self.assertEqual('Changed', self.scalar('SELECT name FROM dds.dim_craft_client WHERE client_id=1'))
        self.assertEqual(0, self.scalar('SELECT count(*) FROM dds.fact_craft_orders WHERE order_id=2'))
        self.assertEqual(0, self.scalar('SELECT count(*) FROM dds.fact_restaurant_orders WHERE order_id=2'))

    def test_postgres_etl_reader_uses_only_the_audit_log(self):
        with self.pg('source') as connection:
            self.assertGreater(connection.execute('SELECT count(*) FROM public.logs').fetchone()[0], 0)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                connection.execute('SELECT * FROM public.client')
            connection.rollback()

    def test_failure_after_stg_and_craft_load_rolls_back_everything(self):
        before = self.snapshot()
        with mongo_client(self.settings, admin=True) as client:
            client[self.settings.get('MONGO_DB')].orders.update_one({'order_id': 1}, {'$set': {'payment': 'invalid-money'}})
        with self.assertRaises(psycopg.errors.InvalidTextRepresentation):
            refresh_warehouse(self.settings)
        self.assertEqual(before, self.snapshot())

    def test_missing_mongo_reference_rolls_back(self):
        before = self.snapshot()
        with mongo_client(self.settings, admin=True) as client:
            client[self.settings.get('MONGO_DB')].orders.update_one({'order_id': 1}, {'$set': {'client_id': 6}})
        with self.assertRaisesRegex(psycopg.Error, 'missing client or restaurant'):
            refresh_warehouse(self.settings)
        self.assertEqual(before, self.snapshot())

    def test_late_commit_is_not_lost_by_log_loading(self):
        with self.pg('source', 'app') as first, self.pg('source', 'app') as second:
            first.execute("UPDATE public.master SET address='First' WHERE master_id=1")
            first_id = first.execute('SELECT max(id) FROM public.logs').fetchone()[0]
            second.execute("UPDATE public.master SET address='Second' WHERE master_id=2")
            second_id = second.execute('SELECT max(id) FROM public.logs').fetchone()[0]
            second.commit()
            refresh_warehouse(self.settings)
            self.assertLess(first_id, second_id)
            self.assertEqual(0, self.scalar('SELECT count(*) FROM stg.pg_logs WHERE id=%s', (first_id,)))
            first.commit()
            refresh_warehouse(self.settings)
            self.assertEqual(2, self.scalar('SELECT count(*) FROM stg.pg_logs WHERE id=ANY(%s)', ([first_id, second_id],)))

    def test_views_commit_rollback_and_reader_permissions(self):
        with self.pg(role='admin', autocommit=True) as writer, self.pg(role='report', autocommit=True) as reader:
            query = "SELECT avg_order_amount_month FROM cdm.craft_customer_monthly WHERE client_id=1 AND report_period='2026-02'"
            old = reader.execute(query).fetchone()[0]
            writer.execute('BEGIN')
            writer.execute('UPDATE dds.fact_craft_orders SET order_price=400 WHERE order_id=1')
            self.assertEqual(old, reader.execute(query).fetchone()[0])
            writer.execute('COMMIT')
            self.assertEqual(Decimal('233.33'), reader.execute(query).fetchone()[0])
            writer.execute('BEGIN')
            writer.execute('UPDATE dds.fact_craft_orders SET order_price=900 WHERE order_id=1')
            writer.execute('ROLLBACK')
            self.assertEqual(Decimal('233.33'), reader.execute(query).fetchone()[0])
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                reader.execute('SELECT * FROM dds.fact_craft_orders')
        with self.pg('source', 'app', autocommit=True) as connection:
            for statement in ('DELETE FROM public.logs', 'UPDATE public.logs SET operation=operation', 'TRUNCATE public.logs'):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    connection.execute(statement)

    def test_one_writer_lock(self):
        before = self.snapshot()
        with self.pg(autocommit=True) as connection:
            connection.execute('SELECT pg_advisory_lock(%s)', (WRITER_LOCK,))
            with self.assertRaisesRegex(RuntimeError, 'Another warehouse refresh'):
                refresh_warehouse(self.settings)
        self.assertEqual(before, self.snapshot())

    def test_legacy_mongo_dates_and_invalid_format(self):
        with self.pg(autocommit=True) as connection:
            for raw in ('01.02.2026 01:30:00', '2026-02-01T01:30:00', '2026-02-01T01:30:00+03:00'):
                actual = connection.execute("SELECT stg.source_timestamp(%s, 'Europe/Moscow')", (Jsonb(raw),)).fetchone()[0]
                self.assertEqual(datetime(2026, 1, 31, 22, 30, tzinfo=timezone.utc), actual)
            self.assertEqual(date(1990, 1, 1), connection.execute('SELECT stg.source_date(%s)',
                             (Jsonb('1990-01-01T00:00:00+03:00'),)).fetchone()[0])
            for raw in ('31.02.2026', 'tomorrow', '2026/02/01'):
                with self.assertRaises(psycopg.Error):
                    connection.execute("SELECT stg.source_timestamp(%s, 'UTC')", (Jsonb(raw),))
        with mongo_client(self.settings, admin=True) as client:
            client[self.settings.get('MONGO_DB')].orders.update_one({'order_id': 1}, {'$set': {'order_date': '01.02.2026 01:30:00'}})
        refresh_warehouse(Settings({**self.settings.values, 'SOURCE_TIMEZONE': 'Europe/Moscow'}))
        self.assertEqual(20260131, self.scalar('SELECT date_key FROM dds.fact_restaurant_orders WHERE order_id=1'))

    def test_csv_normalization_duplicates_and_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for path in (ROOT / 'seeds' / 'csv').glob('*.csv'):
                shutil.copy(path, directory / path.name)
            path = directory / 'user_behavior.csv'
            contents = path.read_text().replace('Id,date_time,behavior_id,user_id,quantity', ' ID , DATE_TIME ,behavior_id, USER_ID ,quantity')
            path.write_text(contents)
            with self.pg('source', 'app') as connection:
                import_csvs(connection, directory, 'Europe/Moscow')
                self.assertEqual(4, connection.execute('SELECT count(*) FROM external_source.user_behavior').fetchone()[0])
                connection.rollback()
            path.write_text(contents + contents.splitlines()[1] + '\n')
            with self.pg('source', 'app') as connection:
                with self.assertRaisesRegex(ValueError, 'duplicate id'):
                    import_csvs(connection, directory, 'Europe/Moscow')
                connection.rollback()
            path.write_text(contents)
            marketing = directory / 'marketing_research.csv'
            marketing.write_text('date_id,category_id,sales_qty,sales_amt\n20260301,123,7,70.00\n')
            with self.pg('source', 'app') as connection:
                with self.assertRaisesRegex(ValueError, 'CSV keys differ'):
                    import_csvs(connection, directory, 'Europe/Moscow')
                import_csvs(connection, directory, 'Europe/Moscow', replace=True)
                self.assertEqual([(1, 20260301, 7, Decimal('70.00'))], connection.execute('SELECT * FROM external_source.marketing_research').fetchall())
                connection.rollback()

    def test_delivery_constraints_and_status_normalization(self):
        with self.pg('source', 'app', autocommit=True) as connection:
            for update in ("status='done', delivery_date=NULL", "status='created', delivery_date=order_date", "status='unknown'"):
                with self.assertRaises(psycopg.errors.CheckViolation):
                    connection.execute(f'UPDATE public."order" SET {update} WHERE order_id=1')
            connection.execute('UPDATE public."order" SET status=%s WHERE order_id=6', ('in progress',))
        refresh_warehouse(self.settings)
        self.assertEqual('in progress', self.scalar('SELECT status FROM stg.pg_public_order WHERE order_id=6'))
        self.assertEqual('in_progress', self.scalar('SELECT status_code FROM dds.fact_craft_orders WHERE order_id=6'))

    def test_large_money_keeps_precision_in_audit_and_stg(self):
        with self.pg('source', 'app') as connection:
            connection.execute('UPDATE public.master_product SET price=%s WHERE id=1', (Decimal('9999999999999999.99'),))
            event_id = connection.execute('SELECT max(id) FROM public.logs').fetchone()[0]
        refresh_warehouse(self.settings)
        self.assertEqual('9999999999999999.99', self.scalar("SELECT object_value->>'price' FROM stg.pg_logs WHERE id=%s", (event_id,)))


if __name__ == '__main__':
    unittest.main()
