
BEGIN;

CREATE SCHEMA IF NOT EXISTS cdm;

-- 17 полей клиентской витрины: одна строка на заказчика и отчётный месяц.
CREATE OR REPLACE VIEW cdm.craft_customer_monthly AS
WITH orders AS (
    -- Цена берётся из снимка заказа. Месяцы создания и завершения считаются отдельно.
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
    -- Для завершённых показателей нужны статус done и фактическая дата завершения.
    SELECT *
    FROM orders
    WHERE status_code = 'done' AND delivery_date IS NOT NULL
), creation_totals AS (
    -- Текущие статусы заказов, созданных в месяце; это не состояние на конец месяца.
    -- В незавершённые входят все статусы, кроме done, включая cancelled.
    SELECT
        client_key,
        created_month AS report_month,
        count(*) AS created_orders_count_month,
        count(*) FILTER (WHERE status_code = 'in_progress') AS in_progress_orders_count_month,
        count(*) FILTER (WHERE status_code <> 'done') AS unfinished_orders_count_month
    FROM orders
    GROUP BY client_key, created_month
), completion_totals AS (
    -- Количество, средняя цена и длительность относятся к месяцу завершения заказа.
    SELECT
        client_key,
        completed_month AS report_month,
        count(*) AS completed_orders_count_month,
        round(avg(order_price), 2) AS avg_order_amount_month,
        -- Медиана длительностей в днях с дробной частью, округлённая до 4 знаков.
        round((
            percentile_cont(0.5) WITHIN GROUP (
                ORDER BY (extract(epoch FROM (delivery_date - order_date)) / 86400.0)::double precision
            )
        )::numeric, 4) AS median_completion_days_month
    FROM completed
    GROUP BY client_key, completed_month
), paid_totals AS (
    -- Все оплаченные заказы за доступную историю независимо от статуса.
    -- Эта сумма будет одинаковой во всех месячных строках одного клиента.
    SELECT client_key, sum(order_price) AS paid_orders_amount_all_time
    FROM orders
    WHERE paid_at IS NOT NULL
    GROUP BY client_key
), category_counts AS (
    -- Популярность непустых категорий по числу завершённых в месяце заказов.
    SELECT client_key, completed_month AS report_month, product_type, count(*) AS orders_count
    FROM completed
    WHERE product_type IS NOT NULL
    GROUP BY client_key, completed_month, product_type
), ranked_categories AS (
    -- При равном количестве выбирается первая категория по COLLATE "C".
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
    -- Популярность мастера считается независимо от популярной категории.
    SELECT client_key, completed_month AS report_month, master_key, count(*) AS orders_count
    FROM completed
    GROUP BY client_key, completed_month, master_key
), ranked_masters AS (
    -- При равном количестве заказов выбирается минимальный исходный master_id.
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
    -- UNION сохраняет и месяцы только с незавершёнными заказами, и месяцы завершения.
    SELECT client_key, report_month FROM creation_totals
    UNION
    SELECT client_key, report_month FROM completion_totals
)
SELECT
    -- Устойчивый ID строки: один и тот же клиент и месяц дают один и тот же хеш.
    md5('craft:' || c.client_id::text || ':' || to_char(p.report_month, 'YYYY-MM'))::varchar(32) AS id,
    c.client_id,
    c.name AS client_name,
    c.address AS client_address,
    c.birthday AS client_birthday,
    c.email AS client_email,
    coalesce(pt.paid_orders_amount_all_time, 0::numeric) AS paid_orders_amount_all_time,
    -- По ТЗ количество заказов за месяц совпадает с количеством завершённых.
    coalesce(ct.completed_orders_count_month, 0::bigint) AS orders_count_month,
    -- Без завершённых заказов среднее, медиана, категория и мастер остаются NULL.
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
-- LEFT JOIN сохраняет клиент-месяц при отсутствии части показателей; счётчики заменяются на 0.
LEFT JOIN creation_totals AS cr ON cr.client_key = p.client_key AND cr.report_month = p.report_month
LEFT JOIN completion_totals AS ct ON ct.client_key = p.client_key AND ct.report_month = p.report_month
LEFT JOIN paid_totals AS pt ON pt.client_key = p.client_key
LEFT JOIN ranked_categories AS rc ON rc.client_key = p.client_key
    AND rc.report_month = p.report_month AND rc.position = 1
LEFT JOIN ranked_masters AS rm ON rm.client_key = p.client_key
    AND rm.report_month = p.report_month AND rm.position = 1;

-- Продажи за день заказа UTC по каждому ресторану: учитываются только закрытые заказы.
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

-- Активность внешнего клиента за день UTC: количество товаров, сумма и события поведения.
CREATE OR REPLACE VIEW cdm.external_client_activity_daily AS
WITH order_events AS (
    -- Каждый факт сначала агрегируется до дня и клиента, чтобы JOIN не умножал суммы.
    SELECT date_key, client_key, sum(quantity) AS quantity, sum(payment_amount) AS payment_amount
    FROM dds.fact_external_order_statuses
    GROUP BY date_key, client_key
), behavior_events AS (
    -- Одна исходная строка поведения равна одному событию: event_count = 1.
    SELECT date_key, client_key, sum(event_count) AS behavior_events_count
    FROM dds.fact_external_user_behavior
    GROUP BY date_key, client_key
), combined AS (
    -- FULL OUTER JOIN сохраняет дни с событиями только одного типа; отсутствующие меры равны 0.
    SELECT
        coalesce(o.date_key, b.date_key) AS date_key,
        coalesce(o.client_key, b.client_key) AS client_key,
        coalesce(o.quantity, 0::numeric) AS quantity,
        coalesce(o.payment_amount, 0::numeric) AS payment_amount,
        coalesce(b.behavior_events_count, 0::numeric) AS behavior_events_count
    FROM order_events AS o
    FULL OUTER JOIN behavior_events AS b USING (date_key, client_key)
)
SELECT d.date_value AS report_date, c.client_id, a.quantity, a.payment_amount, a.behavior_events_count
FROM combined AS a
JOIN dds.dim_date AS d ON d.date_key = a.date_key
JOIN dds.dim_external_client AS c ON c.client_key = a.client_key;

-- Общие продажи маркетингового набора за день, без разделения по клиентам или категориям.
CREATE OR REPLACE VIEW cdm.marketing_daily_sales AS
SELECT d.date_value AS report_date, sum(f.sales_qty) AS sales_qty, sum(f.sales_amt) AS sales_amt
FROM dds.fact_external_marketing_research AS f
JOIN dds.dim_date AS d ON d.date_key = f.date_key
GROUP BY d.date_value;

-- Количество товаров и сумма внешних событий заказа за день UTC по каждому клиенту.
-- Несмотря на имя источника, фактического статуса заказа в этих данных нет.
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

COMMIT;
