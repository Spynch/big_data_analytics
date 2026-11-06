import csv
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from psycopg import sql


def parse_timestamp(value, source_timezone):
    value = value.strip()
    if "." in value:
        timestamp = datetime.strptime(value, "%d.%m.%Y %H:%M:%S")
    else:
        timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=ZoneInfo(source_timezone))
    return timestamp.astimezone(timezone.utc)


def insert_rows(connection, schema, table, columns, rows):
    query = sql.SQL("""
        INSERT INTO {} ({}) VALUES ({})
        ON CONFLICT ({}) DO NOTHING
    """).format(
        sql.Identifier(schema, table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        sql.Identifier(columns[0]),
    )
    with connection.cursor() as cursor:
        cursor.executemany(query, rows)


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        reader.fieldnames = [name.strip().lower() for name in reader.fieldnames]
        return list(reader)


def import_csvs(connection, directory, source_timezone):
    connection.execute("""
        TRUNCATE TABLE
            external_source.order_statuses,
            external_source.user_behavior,
            external_source.marketing_research
    """)
    order_statuses = [
        (
            int(row["id"]),
            parse_timestamp(row["date_time"], source_timezone),
            int(row["client_id"]),
            int(row["quantity"]),
            Decimal(row["payment_amount"]),
        )
        for row in read_csv(directory / "order_statuses.csv")
    ]
    insert_rows(
        connection,
        "external_source",
        "order_statuses",
        ("id", "date_time", "client_id", "quantity", "payment_amount"),
        order_statuses,
    )

    user_behavior = [
        (
            int(row["id"]),
            parse_timestamp(row["date_time"], source_timezone),
            int(row["user_id"]),
        )
        for row in read_csv(directory / "user_behavior.csv")
    ]
    insert_rows(
        connection,
        "external_source",
        "user_behavior",
        ("id", "date_time", "client_id"),
        user_behavior,
    )

    marketing = [
        (
            row_number,
            int(row["date_id"]),
            int(row["sales_qty"]),
            Decimal(row["sales_amt"]),
        )
        for row_number, row in enumerate(
            read_csv(directory / "marketing_research.csv"),
            start=1,
        )
    ]
    insert_rows(
        connection,
        "external_source",
        "marketing_research",
        ("id", "date_id", "sales_qty", "sales_amt"),
        marketing,
    )
