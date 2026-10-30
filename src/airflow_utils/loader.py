import json
from decimal import Decimal

from psycopg import sql
from psycopg.types.json import Jsonb

from airflow_utils.postgres_source import TABLES


def copy_rows(connection, table, columns, rows):
    statement = sql.SQL('COPY {} ({}) FROM STDIN').format(
        sql.Identifier('stg', table), sql.SQL(', ').join(map(sql.Identifier, columns)),
    )
    with connection.cursor().copy(statement) as copy:
        for row in rows:
            copy.write_row(tuple(Jsonb(value) if isinstance(value, dict) else value for value in row))


def apply_postgres_events(connection, events, extracted_at):
    tables = {(table.schema, table.name): table for table in TABLES}
    applied = 0
    for event in events:
        event_id, changed_at, schema, name, operation, raw_payload = event
        inserted = connection.execute(
            'INSERT INTO stg.pg_logs VALUES (%s, %s, %s, %s, %s, %s, %s) '
            'ON CONFLICT (id) DO NOTHING RETURNING id',
            (event_id, changed_at, schema, name, operation,
             Jsonb(raw_payload, dumps=lambda value: value), extracted_at),
        ).fetchone()
        if inserted is None:
            continue
        table = tables.get((schema, name))
        if table is None:
            raise ValueError(f'Unsupported audit object: {schema}.{name}')
        payload = json.loads(raw_payload, parse_float=Decimal)
        key_column = table.columns[0]
        if key_column not in payload:
            raise ValueError(f'Audit event {event_id} has no key {key_column}')
        target = sql.Identifier('stg', table.target)
        connection.execute(
            sql.SQL('DELETE FROM {} WHERE {} = %s').format(
                target, sql.Identifier(key_column)),
            (payload[key_column],),
        )
        if operation in ('INSERT', 'UPDATE'):
            columns = (*table.columns, 'extracted_at')
            query = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                target,
                sql.SQL(', ').join(map(sql.Identifier, columns)),
                sql.SQL(', ').join(sql.Placeholder() for _ in columns),
            )
            values = [payload.get(column) for column in table.columns]
            connection.execute(query, (*values, extracted_at))
        elif operation not in ('DELETE', 'TRUNCATE'):
            raise ValueError(f'Unsupported audit operation: {operation}')
        applied += 1
    return applied


def load_stg(connection, postgres_events, mongo, extracted_at):
    applied = apply_postgres_events(connection, postgres_events, extracted_at)
    for name, rows in mongo.items():
        connection.execute(sql.SQL('DELETE FROM {}').format(sql.Identifier('stg', name)))
        copy_rows(connection, name, ('source_id', 'payload', 'extracted_at'),
                  ((*row, extracted_at) for row in rows))
    return applied
