import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from psycopg.conninfo import make_conninfo
from sqlalchemy import URL

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    values: dict[str, str]

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / '.env')
        settings = cls(dict(os.environ))
        ZoneInfo(settings.get('SOURCE_TIMEZONE'))
        return settings

    def get(self, key):
        value = self.values.get(key)
        if not value:
            raise ValueError(f'Missing setting: {key}')
        return value

    def pg_params(self, target, role='etl'):
        prefix = 'SOURCE' if target == 'source' else 'DWH'
        users = {'etl': f'{prefix}_ETL_USER', 'admin': f'{prefix}_ADMIN',
                 'app': 'SOURCE_APP_USER', 'report': 'REPORT_USER'}
        passwords = {'etl': f'{prefix}_ETL_PASSWORD', 'admin': f'{prefix}_PASSWORD',
                     'app': 'SOURCE_APP_PASSWORD', 'report': 'REPORT_PASSWORD'}
        return dict(host=self.get(f'{prefix}_HOST'),
                    port=int(self.values.get(f'{prefix}_CONNECT_PORT', '5432')),
                    dbname=self.get(f'{prefix}_DB'), user=self.get(users[role]),
                    password=self.get(passwords[role]), connect_timeout=10)

    def dsn(self, target, role='etl'):
        return make_conninfo(**self.pg_params(target, role))

    def migration_url(self, target):
        params = self.pg_params(target, 'admin')
        params['database'] = params.pop('dbname')
        params['username'] = params.pop('user')
        params.pop('connect_timeout')
        return URL.create('postgresql+psycopg', **params)
