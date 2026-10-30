from dataclasses import dataclass

import psycopg
from psycopg import sql


@dataclass(frozen=True)
class SourceTable:
    schema: str
    name: str
    target: str
    columns: tuple[str, ...]


TABLES = (
    SourceTable('public', 'master', 'pg_public_master', ('master_id', 'name', 'phone', 'address', 'birthday')),
    SourceTable('public', 'product', 'pg_public_product', ('product_id', 'name', 'description', 'type')),
    SourceTable('public', 'master_product', 'pg_public_master_product', ('id', 'master_id', 'product_id', 'price')),
    SourceTable('public', 'client', 'pg_public_client', ('client_id', 'name', 'phone', 'address', 'birthday', 'email')),
    SourceTable('public', 'order', 'pg_public_order', ('order_id', 'master_id', 'product_id', 'client_id', 'order_date', 'delivery_date', 'status', 'order_price', 'paid_at')),
    SourceTable('external_source', 'order_statuses', 'pg_external_order_statuses', ('id', 'date_time', 'client_id', 'quantity', 'payment_amount')),
    SourceTable('external_source', 'user_behavior', 'pg_external_user_behavior', ('id', 'date_time', 'client_id')),
    SourceTable('external_source', 'marketing_research', 'pg_external_marketing_research', ('id', 'date_id', 'sales_qty', 'sales_amt')),
)

LOG_COLUMNS = ('id', 'changed_at', 'object_schema', 'object_type', 'operation', 'object_value')


def extract_postgres_events(settings, loaded_ids):
    """Return committed audit events that have not reached STG yet.

    The ID scan deliberately does not use max(id) as a watermark: PostgreSQL
    sequences are allocated before commit, so a lower ID may become visible
    after a higher ID has already been loaded.
    """
    loaded_ids = set(loaded_ids)
    with psycopg.connect(settings.dsn('source')) as connection:
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        source_ids = connection.execute('SELECT id FROM public.logs ORDER BY id').fetchall()
        missing_ids = [row[0] for row in source_ids if row[0] not in loaded_ids]
        if not missing_ids:
            return []
        columns = sql.SQL(', ').join(
            sql.SQL('{}::text').format(sql.Identifier(column))
            if column == 'object_value'
            else sql.Identifier(column)
            for column in LOG_COLUMNS
        )
        query = sql.SQL(
            'SELECT {} FROM public.logs WHERE id = ANY(%s) ORDER BY id'
        ).format(columns)
        return connection.execute(query, (missing_ids,)).fetchall()
