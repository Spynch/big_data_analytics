import json

import pyarrow as pa
from psycopg.rows import dict_row

from warehouse import connections as db
from warehouse.contracts import CDM, arrow_schema
from warehouse.control import canonical
from warehouse.pipeline import SORT_KEYS
from warehouse.settings import ROOT


def normalize(name, rows):
    return canonical(pa.Table.from_pylist(rows, schema=arrow_schema(CDM[name])).to_pylist())


def mart(name):
    with db.clickhouse(reader=True) as client:
        result = client.query(f"SELECT * FROM cdm.{name} ORDER BY {','.join(SORT_KEYS[name])}")
        return normalize(name,[dict(zip(result.column_names,row)) for row in result.result_rows])


def all_marts():
    return {name:mart(name) for name in CDM}


def golden():
    return json.loads((ROOT/'tests/fixtures/craft_customer_monthly.json').read_text(encoding='utf8'))


def assert_golden():
    name = 'craft_customer_monthly'
    expected = golden()
    with db.postgres(row_factory=dict_row) as conn:
        source = conn.execute((ROOT/'sql/source'/f'{name}.sql').read_text()).fetchall()
    with db.trino() as conn:
        cursor = conn.cursor()
        cursor.execute((ROOT/'sql/cdm'/f'{name}.sql').read_text())
        fields = [col[0] for col in cursor.description]
        trino = [dict(zip(fields,row)) for row in cursor.fetchall()]
    assert len(fields) == 17
    assert normalize(name,source) == expected
    assert normalize(name,trino) == expected
    assert mart(name) == expected


def etags():
    from warehouse.settings import setting
    s3 = db.s3()
    return {name:s3.head_object(Bucket=setting('S3_BUCKET'),Key=f'cdm/{name}/current.parquet')['ETag']
            for name in CDM}
