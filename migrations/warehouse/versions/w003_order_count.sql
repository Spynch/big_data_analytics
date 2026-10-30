CREATE SCHEMA IF NOT EXISTS cdm;

CREATE OR REPLACE VIEW cdm.craft_customer_monthly AS
WITH orders AS (
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
    JOIN dds.dim_craft_product AS p ON p.product_key = f.product_key
), completed AS (
    SELECT *
    FROM orders
    WHERE status_code = 'done' AND delivery_date IS NOT NULL
), creation_totals AS (
    SELECT
        client_key,
        created_month AS report_month,
        count(*) AS created_orders_count_month,
        count(*) FILTER (WHERE status_code = 'in_progress') AS in_progress_orders_count_month,
        count(*) FILTER (WHERE status_code <> 'done') AS unfinished_orders_count_month
    FROM orders
    GROUP BY client_key, created_month
), completion_totals AS (
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
    FROM completed
    GROUP BY client_key, completed_month
), paid_totals AS (
    SELECT client_key, sum(order_price) AS paid_orders_amount_all_time
    FROM orders
    WHERE paid_at IS NOT NULL
    GROUP BY client_key
), category_counts AS (
    SELECT client_key, completed_month AS report_month, product_type, count(*) AS orders_count
    FROM completed
    WHERE product_type IS NOT NULL
    GROUP BY client_key, completed_month, product_type
), ranked_categories AS (
    SELECT
        client_key,
        report_month,
        product_type,
        row_number() OVER (
            PARTITION BY client_key, report_month
            ORDER BY orders_count DESC, product_type COLLATE "C" ASC
        ) AS position
    FROM category_counts
), master_counts AS (
    SELECT client_key, completed_month AS report_month, master_key, count(*) AS orders_count
    FROM completed
    GROUP BY client_key, completed_month, master_key
), ranked_masters AS (
    SELECT
        mc.client_key,
        mc.report_month,
        m.master_id,
        row_number() OVER (
            PARTITION BY mc.client_key, mc.report_month
            ORDER BY mc.orders_count DESC, m.master_id ASC
        ) AS position
    FROM master_counts AS mc
    JOIN dds.dim_craft_master AS m ON m.master_key = mc.master_key
), periods AS (
    SELECT client_key, report_month FROM creation_totals
    UNION
    SELECT client_key, report_month FROM completion_totals
)
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
FROM periods AS p
JOIN dds.dim_craft_client AS c ON c.client_key = p.client_key
LEFT JOIN creation_totals AS cr ON cr.client_key = p.client_key AND cr.report_month = p.report_month
LEFT JOIN completion_totals AS ct ON ct.client_key = p.client_key AND ct.report_month = p.report_month
LEFT JOIN paid_totals AS pt ON pt.client_key = p.client_key
LEFT JOIN ranked_categories AS rc ON rc.client_key = p.client_key
    AND rc.report_month = p.report_month AND rc.position = 1
LEFT JOIN ranked_masters AS rm ON rm.client_key = p.client_key
    AND rm.report_month = p.report_month AND rm.position = 1;

