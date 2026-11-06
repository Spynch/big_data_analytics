CREATE SCHEMA IF NOT EXISTS cdm;
CREATE SCHEMA IF NOT EXISTS cdm_internal;

CREATE OR REPLACE VIEW cdm_internal.craft_orders AS
SELECT
    f.client_key,
    f.master_key,
    f.order_date,
    f.delivery_date,
    f.status_code,
    f.order_price,
    f.paid_at,
    NULLIF(btrim(p.product_type), '') AS product_type,
    date_trunc('month', f.order_date AT TIME ZONE 'UTC')::date AS created_month,
    date_trunc('month', f.delivery_date AT TIME ZONE 'UTC')::date AS completed_month
FROM dds.fact_craft_orders AS f
JOIN dds.dim_craft_product AS p ON p.product_key = f.product_key;

CREATE OR REPLACE VIEW cdm_internal.craft_creation_metrics AS
SELECT
    client_key,
    created_month AS report_month,
    count(*) AS created_orders_count_month,
    count(*) FILTER (WHERE status_code = 'in_progress') AS in_progress_orders_count_month,
    count(*) FILTER (WHERE status_code <> 'done') AS unfinished_orders_count_month
FROM cdm_internal.craft_orders
GROUP BY client_key, created_month;

CREATE OR REPLACE VIEW cdm_internal.craft_completion_metrics AS
SELECT
    client_key,
    completed_month AS report_month,
    count(*) AS completed_orders_count_month,
    round(avg(order_price), 2) AS avg_order_amount_month,
    round((
        percentile_cont(0.5) WITHIN GROUP (
            ORDER BY (extract(epoch FROM (delivery_date - order_date)) / 86400.0)::double precision
        )
    )::numeric, 4) AS median_completion_days_month
FROM cdm_internal.craft_orders
WHERE status_code = 'done' AND delivery_date IS NOT NULL
GROUP BY client_key, completed_month;

CREATE OR REPLACE VIEW cdm_internal.craft_paid_totals AS
SELECT client_key, sum(order_price) AS paid_orders_amount_all_time
FROM cdm_internal.craft_orders
WHERE paid_at IS NOT NULL
GROUP BY client_key;

CREATE OR REPLACE VIEW cdm_internal.craft_popular_categories AS
SELECT DISTINCT ON (client_key, completed_month)
    client_key,
    completed_month AS report_month,
    product_type,
    count(*) AS orders_count
FROM cdm_internal.craft_orders
WHERE status_code = 'done' AND delivery_date IS NOT NULL AND product_type IS NOT NULL
GROUP BY client_key, completed_month, product_type
ORDER BY client_key, completed_month, orders_count DESC, product_type COLLATE "C" ASC;

CREATE OR REPLACE VIEW cdm_internal.craft_popular_masters AS
SELECT DISTINCT ON (o.client_key, o.completed_month)
    o.client_key,
    o.completed_month AS report_month,
    m.master_id,
    count(*) AS orders_count
FROM cdm_internal.craft_orders AS o
JOIN dds.dim_craft_master AS m ON m.master_key = o.master_key
WHERE o.status_code = 'done' AND o.delivery_date IS NOT NULL
GROUP BY o.client_key, o.completed_month, m.master_id
ORDER BY o.client_key, o.completed_month, orders_count DESC, m.master_id ASC;

CREATE OR REPLACE VIEW cdm_internal.craft_periods AS
SELECT client_key, report_month FROM cdm_internal.craft_creation_metrics
UNION
SELECT client_key, report_month FROM cdm_internal.craft_completion_metrics;

CREATE OR REPLACE VIEW cdm.craft_customer_monthly AS
SELECT
    md5('craft:' || c.client_id::text || ':' || to_char(p.report_month, 'YYYY-MM'))::varchar(32) AS id,
    c.client_id,
    c.name AS client_name,
    c.address AS client_address,
    c.birthday AS client_birthday,
    c.email AS client_email,
    coalesce(pt.paid_orders_amount_all_time, 0::numeric) AS paid_orders_amount_all_time,
    coalesce(cr.created_orders_count_month, 0::bigint) AS orders_count_month,
    ct.avg_order_amount_month,
    ct.median_completion_days_month,
    rc.product_type AS most_popular_category_month,
    rm.master_id AS most_popular_master_id_month,
    coalesce(cr.created_orders_count_month, 0::bigint) AS created_orders_count_month,
    coalesce(cr.in_progress_orders_count_month, 0::bigint) AS in_progress_orders_count_month,
    coalesce(ct.completed_orders_count_month, 0::bigint) AS completed_orders_count_month,
    coalesce(cr.unfinished_orders_count_month, 0::bigint) AS unfinished_orders_count_month,
    to_char(p.report_month, 'YYYY-MM')::varchar(7) AS report_period
FROM cdm_internal.craft_periods AS p
JOIN dds.dim_craft_client AS c ON c.client_key = p.client_key
LEFT JOIN cdm_internal.craft_creation_metrics AS cr
    ON cr.client_key = p.client_key AND cr.report_month = p.report_month
LEFT JOIN cdm_internal.craft_completion_metrics AS ct
    ON ct.client_key = p.client_key AND ct.report_month = p.report_month
LEFT JOIN cdm_internal.craft_paid_totals AS pt ON pt.client_key = p.client_key
LEFT JOIN cdm_internal.craft_popular_categories AS rc
    ON rc.client_key = p.client_key AND rc.report_month = p.report_month
LEFT JOIN cdm_internal.craft_popular_masters AS rm
    ON rm.client_key = p.client_key AND rm.report_month = p.report_month;

CREATE OR REPLACE VIEW cdm.restaurant_daily_sales AS
SELECT
    d.date_value AS report_date,
    r.restaurant_id,
    r.name AS restaurant_name,
    count(*) AS orders_count,
    sum(f.cost) AS cost_total,
    sum(f.payment) AS payment_total,
    sum(f.bonus_for_visit) AS bonus_for_visit_total
FROM dds.fact_restaurant_orders AS f
JOIN dds.dim_date AS d ON d.date_key = f.date_key
JOIN dds.dim_restaurant AS r ON r.restaurant_key = f.restaurant_key
WHERE f.status_code = 'closed'
GROUP BY d.date_value, r.restaurant_id, r.name;

CREATE OR REPLACE VIEW cdm_internal.external_order_events_daily AS
SELECT date_key, client_key, sum(quantity) AS quantity, sum(payment_amount) AS payment_amount
FROM dds.fact_external_order_statuses
GROUP BY date_key, client_key;

CREATE OR REPLACE VIEW cdm_internal.external_behavior_events_daily AS
SELECT date_key, client_key, sum(event_count) AS behavior_events_count
FROM dds.fact_external_user_behavior
GROUP BY date_key, client_key;

CREATE OR REPLACE VIEW cdm.external_client_activity_daily AS
SELECT
    d.date_value AS report_date,
    c.client_id,
    coalesce(o.quantity, 0::numeric) AS quantity,
    coalesce(o.payment_amount, 0::numeric) AS payment_amount,
    coalesce(b.behavior_events_count, 0::numeric) AS behavior_events_count
FROM cdm_internal.external_order_events_daily AS o
FULL OUTER JOIN cdm_internal.external_behavior_events_daily AS b USING (date_key, client_key)
JOIN dds.dim_date AS d ON d.date_key = coalesce(o.date_key, b.date_key)
JOIN dds.dim_external_client AS c ON c.client_key = coalesce(o.client_key, b.client_key);

CREATE OR REPLACE VIEW cdm.marketing_daily_sales AS
SELECT d.date_value AS report_date, sum(f.sales_qty) AS sales_qty, sum(f.sales_amt) AS sales_amt
FROM dds.fact_external_marketing_research AS f
JOIN dds.dim_date AS d ON d.date_key = f.date_key
GROUP BY d.date_value;

CREATE OR REPLACE VIEW cdm.external_order_statuses_daily AS
SELECT
    d.date_value AS report_date,
    c.client_id,
    sum(f.quantity) AS quantity,
    sum(f.payment_amount) AS payment_amount
FROM dds.fact_external_order_statuses AS f
JOIN dds.dim_date AS d ON d.date_key = f.date_key
JOIN dds.dim_external_client AS c ON c.client_key = f.client_key
GROUP BY d.date_value, c.client_id;

