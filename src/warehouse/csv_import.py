import csv
import re
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from psycopg import sql


def parse_timestamp(raw, source_timezone):
    raw = raw.strip()
    if re.fullmatch(r'\d{2}\.\d{2}\.\d{4}( \d{2}:\d{2}:\d{2})?', raw):
        value = datetime.strptime(raw, '%d.%m.%Y %H:%M:%S' if ' ' in raw else '%d.%m.%Y')
    elif re.fullmatch(r'\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?', raw):
        value = datetime.fromisoformat(raw)
    else:
        raise ValueError(f'Invalid source date: {raw}')
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(source_timezone))
    return value.astimezone(timezone.utc)


def upsert_rows(connection, schema, table, columns, rows, update_columns=None):
    updates = tuple(update_columns or columns[1:])
    assignments = sql.SQL(', ').join(sql.SQL('{} = EXCLUDED.{}').format(sql.Identifier(c), sql.Identifier(c)) for c in updates)
    old = sql.SQL(', ').join(sql.Identifier('current_row', c) for c in updates)
    new = sql.SQL(', ').join(sql.Identifier('excluded', c) for c in updates)
    query = sql.SQL('''
        INSERT INTO {} AS current_row ({}) VALUES ({})
        ON CONFLICT ({}) DO UPDATE SET {} WHERE ({}) IS DISTINCT FROM ({})
    ''').format(sql.Identifier(schema, table), sql.SQL(', ').join(map(sql.Identifier, columns)),
               sql.SQL(', ').join(sql.Placeholder() for _ in columns), sql.Identifier(columns[0]),
               assignments, old, new)
    with connection.cursor() as cursor:
        cursor.executemany(query, rows)


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        headers = [name.strip().lower() for name in reader.fieldnames or []]
        if len(set(headers)) != len(headers):
            raise ValueError(f'{path.name}: duplicate column names')
        reader.fieldnames = headers
        return list(reader)


def import_csvs(connection, directory, source_timezone, replace=False):
    datasets = []
    for name in ('order_statuses', 'user_behavior', 'marketing_research'):
        rows = []
        seen = set()
        for line, raw in enumerate(read_csv(directory / f'{name}.csv'), start=1):
            try:
                key = line if name == 'marketing_research' else int(raw['id'])
                if key in seen:
                    raise ValueError(f'duplicate id {key}')
                seen.add(key)
                if name == 'order_statuses':
                    columns = ('id', 'date_time', 'client_id', 'quantity', 'payment_amount')
                    row = (key, parse_timestamp(raw['date_time'], source_timezone), int(raw['client_id']),
                           int(raw['quantity']), Decimal(raw['payment_amount']))
                elif name == 'user_behavior':
                    columns = ('id', 'date_time', 'client_id')
                    row = (key, parse_timestamp(raw['date_time'], source_timezone), int(raw['user_id']))
                else:
                    columns = ('id', 'date_id', 'sales_qty', 'sales_amt')
                    date_id = raw['date_id'].strip()
                    if not re.fullmatch(r'\d{8}', date_id):
                        raise ValueError('date_id must be YYYYMMDD')
                    datetime.strptime(date_id, '%Y%m%d')
                    row = (key, int(date_id), int(raw['sales_qty']), Decimal(raw['sales_amt']))
                rows.append(row)
            except (KeyError, ValueError, ArithmeticError) as error:
                raise ValueError(f'{name}.csv row {line + 1}: {error}') from error
        if not rows:
            raise ValueError(f'{name}.csv: empty dataset; refusing implicit removal')
        datasets.append((name, columns, rows))
    for name, _, rows in datasets:
        current = {row[0] for row in connection.execute(sql.SQL('SELECT id FROM {}').format(
            sql.Identifier('external_source', name))).fetchall()}
        incoming = {row[0] for row in rows}
        if current and current != incoming and not replace:
            raise ValueError(f'{name}: CSV keys differ from existing data; use explicit --replace for a full replacement')
    for name, columns, rows in datasets:
        upsert_rows(connection, 'external_source', name, columns, rows)
        if replace:
            connection.execute(sql.SQL('DELETE FROM {} WHERE NOT (id = ANY(%s))').format(
                sql.Identifier('external_source', name)), ([row[0] for row in rows],))


if __name__ == '__main__':
    import argparse
    import psycopg
    from warehouse.config import ROOT, Settings

    parser = argparse.ArgumentParser()
    parser.add_argument('--replace', action='store_true', help='Replace all three external_source datasets')
    arguments = parser.parse_args()
    settings = Settings.from_env()
    with psycopg.connect(settings.dsn('source', 'app')) as connection:
        import_csvs(connection, ROOT / 'seeds' / 'csv', settings.get('SOURCE_TIMEZONE'), arguments.replace)
