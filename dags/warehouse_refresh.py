import os
from datetime import datetime, timedelta, timezone

from airflow.sdk import dag, task

from airflow_utils.refresh import import_external_csvs, refresh_warehouse
from warehouse.config import Settings


@dag(
    dag_id="warehouse_refresh",
    start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
    schedule=os.getenv("AIRFLOW_SCHEDULE", "@hourly"),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(seconds=30)},
    tags=["warehouse"],
)
def warehouse_refresh():
    @task(task_id="import_external_csvs", do_xcom_push=False)
    def import_csv():
        import_external_csvs(Settings.from_env())

    @task(task_id="refresh_warehouse", do_xcom_push=False)
    def refresh():
        refresh_warehouse(Settings.from_env())

    import_csv() >> refresh()


warehouse_refresh()
