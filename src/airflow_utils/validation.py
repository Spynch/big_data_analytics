from psycopg import sql

COUNTS = {
    'pg_public_master': 'dim_craft_master',
    'pg_public_product': 'dim_craft_product',
    'pg_public_client': 'dim_craft_client',
    'pg_public_master_product': 'fact_craft_offers',
    'pg_public_order': 'fact_craft_orders',
    'pg_external_order_statuses': 'fact_external_order_statuses',
    'pg_external_user_behavior': 'fact_external_user_behavior',
    'pg_external_marketing_research': 'fact_external_marketing_research',
    'mongo_clients': 'dim_restaurant_client',
    'mongo_restaurant': 'dim_restaurant',
    'mongo_orders': 'fact_restaurant_orders',
}


def validate_warehouse(connection):
    for source, target in COUNTS.items():
        query = sql.SQL('SELECT (SELECT count(*) FROM {}) = (SELECT count(*) FROM {})').format(
            sql.Identifier('stg', source), sql.Identifier('dds', target))
        if not connection.execute(query).fetchone()[0]:
            raise ValueError(f'Row count mismatch: stg.{source} -> dds.{target}')
    if connection.execute('''
        SELECT EXISTS (
            SELECT 1 FROM dds.fact_craft_orders o LEFT JOIN dds.fact_craft_offers p
            ON p.master_key = o.master_key AND p.product_key = o.product_key WHERE p.id IS NULL
        )
    ''').fetchone()[0]:
        raise ValueError('Craft order references a missing master/product offer')
    if connection.execute('''
        SELECT EXISTS (SELECT 1 FROM cdm.craft_customer_monthly
            WHERE orders_count_month < 0 OR created_orders_count_month < 0
                OR completed_orders_count_month < 0 OR unfinished_orders_count_month < 0)
        OR EXISTS (SELECT 1 FROM cdm.craft_customer_monthly
            GROUP BY client_id, report_period HAVING count(*) <> 1)
    ''').fetchone()[0]:
        raise ValueError('Invalid monthly customer grain or order counts')
    kinds = connection.execute('''
        SELECT relkind FROM pg_class JOIN pg_namespace n ON n.oid = relnamespace
        WHERE n.nspname = 'cdm'
    ''').fetchall()
    if kinds != [('v',)] * 5:
        raise ValueError('CDM must contain exactly five ordinary views')
