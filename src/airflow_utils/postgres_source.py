import psycopg


TABLES = {
    ("public", "master"): (
        "pg_public_master",
        ("master_id", "name", "phone", "address", "birthday"),
    ),
    ("public", "product"): (
        "pg_public_product",
        ("product_id", "name", "description", "type"),
    ),
    ("public", "master_product"): (
        "pg_public_master_product",
        ("id", "master_id", "product_id", "price"),
    ),
    ("public", "client"): (
        "pg_public_client",
        ("client_id", "name", "phone", "address", "birthday", "email"),
    ),
    ("public", "order"): (
        "pg_public_order",
        (
            "order_id",
            "master_id",
            "product_id",
            "client_id",
            "order_date",
            "delivery_date",
            "status",
            "order_price",
            "paid_at",
        ),
    ),
}


def extract_postgres_events(settings, last_loaded_id):
    """Читает новые события журнала."""
    query = """
        SELECT id, changed_at, object_schema, object_type, operation, object_value::text
        FROM public.logs
        WHERE id > %s AND object_schema = 'public'
        ORDER BY id
    """
    with psycopg.connect(settings.dsn("source")) as connection:
        return connection.execute(query, (last_loaded_id,)).fetchall()
