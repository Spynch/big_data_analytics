import json
import os
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def run_dag(timeout=300):
    base = 'http://airflow-api-server:8080'
    token = None

    def request(path, method='GET', data=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        body = json.dumps(data).encode() if data is not None else None
        with urlopen(Request(base + path, data=body, headers=headers, method=method), timeout=20) as response:
            return json.load(response)

    token = request('/auth/token', 'POST', {
        'username': os.environ['AIRFLOW_ADMIN'], 'password': os.environ['AIRFLOW_ADMIN_PASSWORD'],
    })['access_token']
    deadline = time.monotonic() + timeout
    path = '/api/v2/dags/warehouse_refresh'
    while True:
        try:
            request(path)
            break
        except HTTPError as error:
            if error.code != 404 or time.monotonic() >= deadline:
                raise
            time.sleep(2)
    request(path, 'PATCH', {'is_paused': False})
    run_id = 'manual__' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    request(path + '/dagRuns', 'POST', {'dag_run_id': run_id, 'logical_date': None, 'conf': {}})
    while time.monotonic() < deadline:
        result = request(path + '/dagRuns/' + run_id)
        if result['state'] == 'success':
            print(f'warehouse_refresh {run_id}: success')
            return
        if result['state'] == 'failed':
            raise RuntimeError(f'warehouse_refresh {run_id} failed; check Airflow task logs')
        time.sleep(2)
    raise TimeoutError(f'warehouse_refresh {run_id} did not finish within {timeout}s')


if __name__ == '__main__':
    run_dag()
