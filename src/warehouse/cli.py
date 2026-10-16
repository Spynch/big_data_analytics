"""All administrative operations run inside the runtime container."""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .settings import ROOT, setting


def trigger(run_id=None, timeout=1200):
    import requests
    base = "http://airflow-api-server:8080"
    auth = requests.post(base+"/auth/token",json={"username":setting("AIRFLOW_ADMIN"),
                         "password":setting("AIRFLOW_ADMIN_PASSWORD")},timeout=30)
    auth.raise_for_status()
    headers = {"Authorization":"Bearer " + auth.json()["access_token"]}
    url = base+"/api/v2/dags/warehouse_pipeline"
    deadline = time.monotonic()+timeout
    while True:
        response = requests.get(url,headers=headers,timeout=30)
        if response.status_code == 200:
            break
        if response.status_code != 404 or time.monotonic()>deadline:
            response.raise_for_status()
            raise TimeoutError("Airflow DAG registration timeout")
        time.sleep(2)
    response = requests.patch(url,headers=headers,json={"is_paused":False},timeout=30)
    response.raise_for_status()
    run_id = run_id or "manual__" + datetime.now(timezone.utc).isoformat()
    response = requests.post(url+"/dagRuns",headers=headers,
        json={"dag_run_id":run_id,"logical_date":datetime.now(timezone.utc).isoformat()},timeout=30)
    response.raise_for_status()
    from urllib.parse import quote
    run_url = url+"/dagRuns/"+quote(run_id,safe="")
    print(f"Triggered Airflow run {run_id}",flush=True)
    last = None
    while time.monotonic()<deadline:
        response = requests.get(run_url,headers=headers,timeout=30)
        response.raise_for_status()
        state = response.json()["state"]
        if state != last:
            print("Airflow state: " + state,flush=True)
            last = state
        if state == "success": return run_id
        if state == "failed":
            tasks = requests.get(run_url+"/taskInstances",headers=headers,timeout=30)
            print(tasks.text)
            raise RuntimeError(f"Airflow run failed: {run_id}")
        time.sleep(3)
    raise TimeoutError(f"Airflow run did not finish within {timeout}s: {run_id}")


def status():
    from alembic import command
    from alembic.config import Config
    from .connections import postgres
    for target in ["postgres","control","clickhouse"]:
        print("Migration status: " + target,flush=True)
        command.current(Config(str(ROOT/f"alembic-{target}.ini")),verbose=True)
    with postgres("control") as conn:
        for table in ["lake_migrations","batches","publications"]:
            print(table,conn.execute(f"SELECT * FROM {table}").fetchall())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command",choices=["bootstrap-meta","bootstrap-catalog","bootstrap-cdm","bootstrap-airflow",
        "migrate","seed","pipeline","trigger","demo","status","test","smoke","fingerprint"])
    parser.add_argument("target",nargs="?")
    parser.add_argument("--run-id")
    parser.add_argument("--csv-dir",type=Path)
    args = parser.parse_args()
    if args.command.startswith("bootstrap-"):
        from . import bootstrap
        {"bootstrap-meta":bootstrap.meta,"bootstrap-catalog":bootstrap.lakekeeper,
         "bootstrap-cdm":bootstrap.empty_cdm,"bootstrap-airflow":bootstrap.airflow}[args.command]()
    elif args.command == "migrate":
        from .migrate import run
        if args.target not in ["postgres","control","clickhouse","lake"]:
            parser.error("migrate needs postgres, control, clickhouse or lake")
        run(args.target)
    elif args.command in ("seed","demo"):
        from .seed import run
        run(args.csv_dir)
        if args.command == "demo": trigger(args.run_id)
    elif args.command == "trigger": trigger(args.run_id)
    elif args.command == "pipeline":
        from .pipeline import run
        print(run(args.run_id or "cli__"+datetime.now(timezone.utc).isoformat()))
    elif args.command == "status": status()
    elif args.command == "fingerprint":
        from .diagnostics import fingerprint
        print(json.dumps(fingerprint(),sort_keys=True))
    else:
        test_path = "tests/integration" if args.command == "test" else "tests/integration/test_smoke.py"
        subprocess.run([sys.executable,"-m","pytest","-q","-p","no:cacheprovider",test_path],check=True,cwd=ROOT)


if __name__ == "__main__":
    main()
