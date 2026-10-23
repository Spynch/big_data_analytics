import psycopg

from warehouse.config import Settings
from airflow_utils.validation import validate_warehouse


def smoke(settings):
    with psycopg.connect(settings.dsn('warehouse')) as connection:
        validate_warehouse(connection)
        if connection.execute('SELECT count(*) FROM dds.fact_craft_orders').fetchone()[0] == 0:
            raise ValueError('Warehouse is empty; run the DAG first')
    with psycopg.connect(settings.dsn('warehouse', 'report')) as connection:
        for name in ('craft_customer_monthly', 'restaurant_daily_sales', 'external_client_activity_daily',
                     'marketing_daily_sales', 'external_order_statuses_daily'):
            rows = connection.execute(f'SELECT * FROM cdm.{name} LIMIT 5').fetchall()
            print(f'{name}: {rows}')


if __name__ == '__main__':
    smoke(Settings.from_env())
