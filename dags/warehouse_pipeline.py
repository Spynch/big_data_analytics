"""A single manual DAG; source extraction tasks join at a common validation barrier."""
import os
from datetime import datetime, timedelta, timezone
from airflow.sdk import dag, task, get_current_context


@dag(dag_id="warehouse_pipeline",schedule=os.environ.get("AIRFLOW_SCHEDULE") or None,
     start_date=datetime(2026,1,1,tzinfo=timezone.utc),catchup=False,max_active_runs=1,
     default_args={"retries":2,"retry_delay":timedelta(seconds=10)},tags=["warehouse","educational"])
def warehouse_pipeline():
    @task
    def check_dependencies():
        from warehouse.pipeline import check_dependencies as check
        return check(get_current_context()["run_id"])

    @task
    def step(name,batch):
        from warehouse.pipeline import execute_step
        return execute_step(name,batch)

    batch = check_dependencies()
    pg = step.override(task_id="extract_postgres_snapshot_and_logs")("extract_postgres_snapshot_and_logs",batch)
    mg = step.override(task_id="extract_mongo_snapshot")("extract_mongo_snapshot",batch)
    barrier = step.override(task_id="validate_stg")("validate_stg",batch)
    [pg,mg] >> barrier
    previous = barrier
    for name in ["build_dimensions","build_facts","validate_dds","calculate_and_publish_cdm","verify_clickhouse","mark_batch_success"]:
        current = step.override(task_id=name)(name,batch)
        previous >> current
        previous = current


warehouse_pipeline()
