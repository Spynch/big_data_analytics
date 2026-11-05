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
    ("external_source", "order_statuses"): (
        "pg_external_order_statuses",
        ("id", "date_time", "client_id", "quantity", "payment_amount"),
    ),
    ("external_source", "user_behavior"): (
        "pg_external_user_behavior",
        ("id", "date_time", "client_id"),
    ),
    ("external_source", "marketing_research"): (
        "pg_external_marketing_research",
        ("id", "date_id", "sales_qty", "sales_amt"),
    ),
}


def extract_postgres_events(settings, last_loaded_id):
    """Читает новые события журнала."""
    query = """
        SELECT id, changed_at, object_schema, object_type, operation, object_value::text
        FROM public.logs
        WHERE id > %s
        ORDER BY id
    """
    with psycopg.connect(settings.dsn("source")) as connection:
        return connection.execute(query, (last_loaded_id,)).fetchall()
