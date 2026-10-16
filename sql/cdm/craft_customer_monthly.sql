-- Run in a Trino session with time_zone = REPORT_TIMEZONE (default UTC).
WITH orders AS (
    SELECT o.*, c.client_id, p.product_type, m.master_id,
           format_datetime(at_timezone(o.order_date, current_timezone()), 'yyyy-MM') AS created_month,
           format_datetime(at_timezone(o.delivery_date, current_timezone()), 'yyyy-MM') AS delivered_month
    FROM lake.dds.fact_craft_orders o
    JOIN lake.dds.dim_craft_client c ON c.client_key = o.client_key
    JOIN lake.dds.dim_craft_product p ON p.product_key = o.product_key
    JOIN lake.dds.dim_craft_master m ON m.master_key = o.master_key
), created AS (
    SELECT client_id, created_month AS report_period,
           count(*) AS created_count,
           count_if(status_code = 'in_progress') AS progress_count,
           count_if(status_code <> 'done') AS unfinished_count
    FROM orders GROUP BY client_id, created_month
), done AS (
    SELECT * FROM orders WHERE status_code = 'done'
), completed AS (
    SELECT client_id, delivered_month AS report_period, count(*) AS completed_count,
           CAST(round(avg(CAST(order_price AS DECIMAL(38,4))), 2) AS DECIMAL(38,2)) AS average_amount,
           array_agg(date_diff('millisecond', order_date, delivery_date)
                     ORDER BY date_diff('millisecond', order_date, delivery_date)) AS durations
    FROM done GROUP BY client_id, delivered_month
), paid AS (
    SELECT client_id, CAST(sum(order_price) AS DECIMAL(38,2)) AS paid_amount
    FROM orders WHERE paid_at IS NOT NULL GROUP BY client_id
), categories AS (
    SELECT client_id, delivered_month AS report_period, nullif(trim(product_type), '') AS category,
           row_number() OVER (PARTITION BY client_id, delivered_month
                              ORDER BY count(*) DESC, nullif(trim(product_type), '') ASC) AS rank
    FROM done WHERE nullif(trim(product_type), '') IS NOT NULL
    GROUP BY client_id, delivered_month, nullif(trim(product_type), '')
), masters AS (
    SELECT client_id, delivered_month AS report_period, master_id,
           row_number() OVER (PARTITION BY client_id, delivered_month
                              ORDER BY count(*) DESC, master_id ASC) AS rank
    FROM done GROUP BY client_id, delivered_month, master_id
), periods AS (
    SELECT client_id, report_period FROM created
    UNION
    SELECT client_id, report_period FROM completed
)
SELECT lower(to_hex(sha256(to_utf8('craft:client:' || CAST(p.client_id AS VARCHAR) || '|' || p.report_period)))) AS id,
       p.client_id, c.name AS client_name, c.address AS client_address,
       c.birthday AS client_birthday, c.email AS client_email,
       coalesce(a.paid_amount, DECIMAL '0.00') AS paid_orders_amount_all_time,
       coalesce(d.completed_count, BIGINT '0') AS orders_count_month,
       d.average_amount AS avg_order_amount_month,
       CAST(round((CAST(element_at(d.durations, (cardinality(d.durations) + 1) / 2) AS DECIMAL(30,8))
                       + CAST(element_at(d.durations, (cardinality(d.durations) + 2) / 2) AS DECIMAL(30,8)))
                   / DECIMAL '2.0' / DECIMAL '86400000.0', 4) AS DECIMAL(18,4)) AS median_completion_days_month,
       cat.category AS most_popular_category_month,
       m.master_id AS most_popular_master_id_month,
       coalesce(cr.created_count, BIGINT '0') AS created_orders_count_month,
       coalesce(cr.progress_count, BIGINT '0') AS in_progress_orders_count_month,
       coalesce(d.completed_count, BIGINT '0') AS completed_orders_count_month,
       coalesce(cr.unfinished_count, BIGINT '0') AS unfinished_orders_count_month,
       p.report_period
FROM periods p
JOIN lake.dds.dim_craft_client c ON c.client_id = p.client_id
LEFT JOIN created cr ON cr.client_id = p.client_id AND cr.report_period = p.report_period
LEFT JOIN completed d ON d.client_id = p.client_id AND d.report_period = p.report_period
LEFT JOIN paid a ON a.client_id = p.client_id
LEFT JOIN categories cat ON cat.client_id = p.client_id AND cat.report_period = p.report_period AND cat.rank = 1
LEFT JOIN masters m ON m.client_id = p.client_id AND m.report_period = p.report_period AND m.rank = 1
ORDER BY p.client_id, p.report_period
