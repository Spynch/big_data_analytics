DELETE FROM dds.fact_craft_orders;
DELETE FROM dds.fact_craft_offers;
DELETE FROM dds.fact_restaurant_orders;
DELETE FROM dds.fact_external_order_statuses;
DELETE FROM dds.fact_external_user_behavior;
DELETE FROM dds.fact_external_marketing_research;
DELETE FROM dds.dim_craft_client;
DELETE FROM dds.dim_craft_master;
DELETE FROM dds.dim_craft_product;
DELETE FROM dds.dim_craft_order_status;
DELETE FROM dds.dim_restaurant_client;
DELETE FROM dds.dim_restaurant;
DELETE FROM dds.dim_restaurant_order_status;
DELETE FROM dds.dim_external_client;
DELETE FROM dds.dim_date;

INSERT INTO dds.dim_date
WITH dates AS (
    SELECT (order_date AT TIME ZONE 'UTC')::date AS day FROM stg.pg_public_order
    UNION SELECT (delivery_date AT TIME ZONE 'UTC')::date FROM stg.pg_public_order WHERE delivery_date IS NOT NULL
    UNION SELECT (date_time AT TIME ZONE 'UTC')::date FROM stg.pg_external_order_statuses
    UNION SELECT (date_time AT TIME ZONE 'UTC')::date FROM stg.pg_external_user_behavior
    UNION SELECT stg.marketing_date(date_id) FROM stg.pg_external_marketing_research
    UNION SELECT (stg.source_timestamp(payload->'order_date', current_setting('warehouse.source_timezone')) AT TIME ZONE 'UTC')::date
          FROM stg.mongo_orders
)
SELECT to_char(day, 'YYYYMMDD')::integer, day, extract(year FROM day), extract(quarter FROM day),
    extract(month FROM day), extract(day FROM day) FROM dates;

INSERT INTO dds.dim_craft_client
SELECT client_id, client_id, name, phone, address, birthday, email FROM stg.pg_public_client;
INSERT INTO dds.dim_craft_master
SELECT master_id, master_id, name, phone, address, birthday FROM stg.pg_public_master;
INSERT INTO dds.dim_craft_product
SELECT product_id, product_id, name, description, type FROM stg.pg_public_product;
INSERT INTO dds.dim_craft_order_status VALUES ('created'), ('in_progress'), ('delivery'), ('done'), ('cancelled');

INSERT INTO dds.dim_restaurant_client
SELECT stg.bson_text(payload->'client_id')::bigint, stg.bson_text(payload->'client_id')::bigint,
    source_id, payload->>'name', payload->>'phone', payload->>'email',
    stg.source_date(payload->'birthday'), payload->>'login', nullif(payload->'address', 'null'::jsonb)
FROM stg.mongo_clients;
INSERT INTO dds.dim_restaurant
SELECT stg.bson_text(payload->'restaurant_id')::bigint, stg.bson_text(payload->'restaurant_id')::bigint,
    source_id, payload->>'name', payload->>'phone', payload->>'email',
    stg.source_date(payload->'founding_day'), payload->>'address'
FROM stg.mongo_restaurant;
INSERT INTO dds.dim_restaurant_order_status
SELECT DISTINCT payload->>'final_status' FROM stg.mongo_orders;
INSERT INTO dds.dim_external_client
SELECT client_id, client_id FROM stg.pg_external_order_statuses
UNION SELECT client_id, client_id FROM stg.pg_external_user_behavior;

INSERT INTO dds.fact_craft_offers
SELECT id, master_id, product_id, price FROM stg.pg_public_master_product;
INSERT INTO dds.fact_craft_orders
SELECT order_id, client_id, master_id, product_id, replace(status, ' ', '_'),
    to_char(order_date AT TIME ZONE 'UTC', 'YYYYMMDD')::integer,
    to_char(delivery_date AT TIME ZONE 'UTC', 'YYYYMMDD')::integer,
    order_date, delivery_date, order_price, paid_at
FROM stg.pg_public_order;
INSERT INTO dds.fact_restaurant_orders
SELECT stg.bson_text(payload->'order_id')::bigint, source_id,
    to_char(parsed.order_date AT TIME ZONE 'UTC', 'YYYYMMDD')::integer,
    stg.bson_text(payload->'client_id')::bigint, stg.bson_text(payload->'restaurant_id')::bigint,
    payload->>'final_status', parsed.order_date,
    stg.bson_text(payload->'cost')::numeric(18,2), stg.bson_text(payload->'payment')::numeric(18,2),
    stg.bson_text(payload->'payed_by_bonuses')::numeric(18,2), stg.bson_text(payload->'bonus_for_visit')::numeric(18,2)
FROM stg.mongo_orders
CROSS JOIN LATERAL (SELECT stg.source_timestamp(payload->'order_date', current_setting('warehouse.source_timezone')) AS order_date) parsed;
INSERT INTO dds.fact_external_order_statuses
SELECT id, to_char(date_time AT TIME ZONE 'UTC', 'YYYYMMDD')::integer, client_id, date_time, quantity, payment_amount
FROM stg.pg_external_order_statuses;
INSERT INTO dds.fact_external_user_behavior
SELECT id, to_char(date_time AT TIME ZONE 'UTC', 'YYYYMMDD')::integer, client_id, date_time, 1
FROM stg.pg_external_user_behavior;
INSERT INTO dds.fact_external_marketing_research
SELECT id, date_id, sales_qty, sales_amt FROM stg.pg_external_marketing_research;
