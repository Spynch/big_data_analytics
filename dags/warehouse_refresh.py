from datetime import datetime, timedelta, timezone
import os

from airflow.sdk import dag, task


@dag(
    dag_id='warehouse_refresh',
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=os.getenv('AIRFLOW_SCHEDULE', '@hourly'),
    catchup=False,
    max_active_runs=1,
    default_args={'retries': 1, 'retry_delay': timedelta(seconds=30)},
    tags=['warehouse'],
)
def warehouse_refresh():
    @task(task_id='refresh_warehouse', do_xcom_push=False)
    def refresh():
        from warehouse.config import Settings
        from airflow_utils.refresh import refresh_warehouse

        refresh_warehouse(Settings.from_env())

    refresh()


warehouse_refresh()
