"""Explicit column contracts. Types are identical across Arrow, Iceberg and SQL."""

# Each tuple is (name, logical type, nullable). No inference from the first batch.
def columns(spec):
    result = []
    for item in spec.split():
        name, typ = item.split(":")
        result.append((name, typ.rstrip("?"), typ.endswith("?")))
    return result


PG = {
    "pg_public_master": ("public", "master", "master_id", columns(
        "master_id:long name:str phone:str? address:str? birthday:date?")),
    "pg_public_product": ("public", "product", "product_id", columns(
        "product_id:long name:str description:str? type:str?")),
    "pg_public_master_product": ("public", "master_product", "id", columns(
        "id:long master_id:long product_id:long price:money")),
    "pg_public_client": ("public", "client", "client_id", columns(
        "client_id:long name:str phone:str? address:str? birthday:date? email:str?")),
    "pg_public_order": ("public", "order", "order_id", columns(
        "order_id:long master_id:long product_id:long client_id:long order_date:time "
        "delivery_date:time? status:str order_price:money? paid_at:time?")),
    "pg_external_order_statuses": ("external_source", "order_statuses", "id", columns(
        "id:long date_time:time client_id:long quantity:long payment_amount:money")),
    "pg_external_user_behavior": ("external_source", "user_behavior", "id", columns(
        "id:long date_time:time client_id:long")),
    "pg_external_marketing_research": ("external_source", "marketing_research", "id", columns(
        "id:long date_id:int sales_qty:long sales_amt:money")),
    "pg_logs": ("public", "logs", "id", columns(
        "log_id:long changed_at:time object_schema:str object_type:str operation:str object_value:str")),
}
MONGO = {
    "mongo_clients": ("clients", columns(
        "_id:str client_id:long name:str phone:str? email:str? login:str? birthday:date? "
        "address:str? update_time:time")),
    "mongo_restaurant": ("restaurant", columns(
        "_id:str restaurant_id:long name:str phone:str? email:str? founding_day:date? address:str?")),
    "mongo_orders": ("orders", columns(
        "_id:str order_id:long restaurant_id:long client_id:long order_date:time ordered_dish:str "
        "payed_by_bonuses:money cost:money payment:money bonus_for_visit:money final_status:str update_time:time")),
}
META = columns("batch_id:str source_system:str source_schema:str? source_pk:str extracted_at:time payload:str")
STG = {name: META + definition[-1] for name, definition in {**PG, **MONGO}.items()}

DDS = {
    "dim_date": columns("date_key:int date_value:date year:int quarter:int month:int day:int"),
    "dim_craft_client": columns("client_key:str client_id:long name:str phone:str? address:str? birthday:date? email:str?"),
    "dim_craft_master": columns("master_key:str master_id:long name:str phone:str? address:str? birthday:date?"),
    "dim_craft_product": columns("product_key:str product_id:long name:str description:str? product_type:str?"),
    "dim_craft_order_status": columns("status_code:str"),
    "dim_restaurant_client": columns("client_key:str client_id:long mongo_id:str name:str phone:str? email:str? login:str? birthday:date? address:str?"),
    "dim_restaurant": columns("restaurant_key:str restaurant_id:long mongo_id:str name:str phone:str? email:str? founding_day:date? address:str?"),
    "dim_restaurant_order_status": columns("status_code:str"),
    "dim_external_client": columns("client_key:str client_id:long"),
    "fact_craft_orders": columns("order_id:long created_date_key:int delivery_date_key:int? client_key:str master_key:str product_key:str status_code:str order_date:time delivery_date:time? order_price:money paid_at:time?"),
    "fact_craft_offers": columns("id:long master_key:str product_key:str price:money"),
    "fact_restaurant_orders": columns("order_id:long date_key:int client_key:str restaurant_key:str status_code:str order_date:time cost:money payment:money payed_by_bonuses:money bonus_for_visit:money"),
    "fact_external_order_statuses": columns("id:long date_key:int client_key:str date_time:time quantity:long payment_amount:money"),
    "fact_external_user_behavior": columns("id:long date_key:int client_key:str date_time:time event_count:long"),
    "fact_external_marketing_research": columns("id:long date_key:int sales_qty:long sales_amt:money"),
}
CDM = {
    "craft_customer_monthly": columns(
        "id:str client_id:long client_name:str client_address:str? client_birthday:date? client_email:str? "
        "paid_orders_amount_all_time:total orders_count_month:long avg_order_amount_month:total? "
        "median_completion_days_month:days? most_popular_category_month:str? most_popular_master_id_month:long? "
        "created_orders_count_month:long in_progress_orders_count_month:long completed_orders_count_month:long "
        "unfinished_orders_count_month:long report_period:str"),
    "restaurant_daily_sales": columns("report_date:date restaurant_id:long restaurant_name:str orders_count:long cost_total:total payment_total:total bonus_for_visit_total:total"),
    "external_client_activity_daily": columns("report_date:date client_id:long behavior_events_count:long quantity_total:long payment_amount_total:total"),
    "marketing_daily_sales": columns("report_date:date sales_qty:long sales_amt:total"),
    "external_order_statuses_daily": columns("report_date:date client_id:long quantity_total:long payment_amount_total:total"),
}


def arrow_schema(definition):
    import pyarrow as pa
    types = {"str": pa.string(), "long": pa.int64(), "int": pa.int32(), "date": pa.date32(),
             "time": pa.timestamp("us", tz="UTC"), "money": pa.decimal128(18, 2),
             "total": pa.decimal128(38, 2), "days": pa.decimal128(18, 4)}
    return pa.schema([pa.field(name, types[typ], nullable=nullable) for name, typ, nullable in definition])


def sql_type(typ):
    return {"str": "VARCHAR", "long": "BIGINT", "int": "INTEGER", "date": "DATE",
            "time": "TIMESTAMP(6) WITH TIME ZONE", "money": "DECIMAL(18,2)",
            "total": "DECIMAL(38,2)", "days": "DECIMAL(18,4)"}[typ]


def ch_columns(definition):
    types = {"str":"String", "long":"Int64", "int":"Int32", "date":"Date32",
             "time":"DateTime64(6, 'UTC')", "money":"Decimal(18,2)",
             "total":"Decimal(38,2)", "days":"Decimal(18,4)"}
    return ", ".join(f"`{n}` " + (f"Nullable({types[t]})" if null else types[t]) for n,t,null in definition)
