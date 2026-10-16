-- Optional: SET warehouse.report_timezone = 'Europe/Moscow'; otherwise UTC.
WITH settings AS (
    SELECT coalesce(nullif(current_setting('warehouse.report_timezone', true), ''), 'UTC') AS tz
), orders AS (
    SELECT o.*, p.type AS product_type,
           to_char(o.order_date AT TIME ZONE s.tz, 'YYYY-MM') AS created_month,
           to_char(o.delivery_date AT TIME ZONE s.tz, 'YYYY-MM') AS delivered_month
    FROM public."order" o JOIN public.product p USING(product_id) CROSS JOIN settings s
), created AS (
    SELECT client_id, created_month AS report_period, count(*) AS created_count,
           count(*) FILTER(WHERE status = 'in_progress') AS progress_count,
           count(*) FILTER(WHERE status <> 'done') AS unfinished_count
    FROM orders GROUP BY client_id, created_month
), done AS (
    SELECT * FROM orders WHERE status = 'done'
), completed AS (
    SELECT client_id, delivered_month AS report_period, count(*) AS completed_count,
           round(avg(order_price), 2)::numeric(38,2) AS average_amount,
           round((percentile_cont(0.5) WITHIN GROUP
             (ORDER BY trunc(extract(epoch FROM (delivery_date-order_date))*1000)))::numeric
             / 86400000, 4)::numeric(18,4) AS median_days
    FROM done GROUP BY client_id, delivered_month
), paid AS (
    SELECT client_id, sum(order_price)::numeric(38,2) AS paid_amount
    FROM orders WHERE paid_at IS NOT NULL GROUP BY client_id
), categories AS (
    SELECT client_id, delivered_month AS report_period, nullif(trim(product_type), '') AS category,
           row_number() OVER (PARTITION BY client_id, delivered_month
             ORDER BY count(*) DESC, nullif(trim(product_type), '') COLLATE "C" ASC) AS rank
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
SELECT encode(sha256(convert_to('craft:client:' || p.client_id::text || '|' || p.report_period, 'UTF8')), 'hex') AS id,
       p.client_id, c.name AS client_name, c.address AS client_address,
       c.birthday AS client_birthday, c.email AS client_email,
       coalesce(a.paid_amount, 0)::numeric(38,2) AS paid_orders_amount_all_time,
       coalesce(d.completed_count, 0) AS orders_count_month,
       d.average_amount AS avg_order_amount_month,
       d.median_days AS median_completion_days_month,
       cat.category AS most_popular_category_month,
       m.master_id AS most_popular_master_id_month,
       coalesce(cr.created_count, 0) AS created_orders_count_month,
       coalesce(cr.progress_count, 0) AS in_progress_orders_count_month,
       coalesce(d.completed_count, 0) AS completed_orders_count_month,
       coalesce(cr.unfinished_count, 0) AS unfinished_orders_count_month,
       p.report_period
FROM periods p JOIN public.client c USING(client_id)
LEFT JOIN created cr ON cr.client_id = p.client_id AND cr.report_period = p.report_period
LEFT JOIN completed d ON d.client_id = p.client_id AND d.report_period = p.report_period
LEFT JOIN paid a ON a.client_id = p.client_id
LEFT JOIN categories cat ON cat.client_id = p.client_id AND cat.report_period = p.report_period AND cat.rank = 1
LEFT JOIN masters m ON m.client_id = p.client_id AND m.report_period = p.report_period AND m.rank = 1
ORDER BY p.client_id, p.report_period
