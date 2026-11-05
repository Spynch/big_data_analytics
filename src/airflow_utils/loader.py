import json
from decimal import Decimal

from psycopg import sql
from psycopg.types.json import Jsonb

from airflow_utils.postgres_source import TABLES


def copy_rows(connection, table, columns, rows):
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier("stg", table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
    )
    with connection.cursor().copy(statement) as copy:
        for row in rows:
            values = (Jsonb(value) if isinstance(value, dict) else value for value in row)
            copy.write_row(tuple(values))


def apply_postgres_events(connection, events, extracted_at):
    for event in events:
        event_id, changed_at, schema, name, operation, raw_payload = event
        connection.execute(
            "INSERT INTO stg.pg_logs VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                event_id,
                changed_at,
                schema,
                name,
                operation,
                Jsonb(raw_payload, dumps=lambda value: value),
                extracted_at,
            ),
        )
        target_table, columns = TABLES[(schema, name)]
        payload = json.loads(raw_payload, parse_float=Decimal)
        key_column = columns[0]
        target = sql.Identifier("stg", target_table)
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE {} = %s").format(target, sql.Identifier(key_column)),
            (payload[key_column],),
        )
        if operation in ("INSERT", "UPDATE"):
            target_columns = (*columns, "extracted_at")
            query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                target,
                sql.SQL(", ").join(map(sql.Identifier, target_columns)),
                sql.SQL(", ").join(sql.Placeholder() for _ in target_columns),
            )
            values = [payload[column] for column in columns]
            connection.execute(query, (*values, extracted_at))
    return len(events)


def load_stg(connection, postgres_events, mongo, extracted_at):
    applied = apply_postgres_events(connection, postgres_events, extracted_at)
    for name, rows in mongo.items():
        connection.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier("stg", name)))
        copy_rows(
            connection,
            name,
            ("source_id", "payload", "extracted_at"),
            ((*row, extracted_at) for row in rows),
        )
    return applied
