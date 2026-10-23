import json
import os
import sys
from pathlib import Path

from sqlalchemy import URL


def main():
    os.environ['AIRFLOW__DATABASE__SQL_ALCHEMY_CONN'] = URL.create(
        'postgresql+psycopg', username=os.environ['AIRFLOW_DB_USER'],
        password=os.environ['AIRFLOW_DB_PASSWORD'], host='postgres-dwh',
        port=5432, database=os.environ['AIRFLOW_DB'],
    ).render_as_string(hide_password=False)
    if sys.argv[1:] == ['db', 'migrate']:
        path = Path(os.environ['AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE'])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({os.environ['AIRFLOW_ADMIN']: os.environ['AIRFLOW_ADMIN_PASSWORD']}))
        path.chmod(0o600)
    os.execvp('airflow', ['airflow', *sys.argv[1:]])


if __name__ == '__main__':
    main()
