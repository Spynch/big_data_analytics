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


def load_stg(connection, postgres, mongo, extracted_at):
    for table in TABLES:
        columns = (*table.columns, 'extracted_at')
        rows = [(*row, extracted_at) for row in postgres[table.target]]
        if table.target == 'pg_logs':
            with connection.cursor() as cursor:
                cursor.executemany(
                    'INSERT INTO stg.pg_logs VALUES (%s, %s, %s, %s, %s, %s, %s) '
                    'ON CONFLICT (id) DO NOTHING',
                    [(*row[:5], Jsonb(row[5], dumps=lambda value: value), row[6]) for row in rows],
                )
        else:
            connection.execute(sql.SQL('DELETE FROM {}').format(sql.Identifier('stg', table.target)))
            copy_rows(connection, table.target, columns, rows)
    for name, rows in mongo.items():
        connection.execute(sql.SQL('DELETE FROM {}').format(sql.Identifier('stg', name)))
        copy_rows(connection, name, ('source_id', 'payload', 'extracted_at'),
                  ((*row, extracted_at) for row in rows))
