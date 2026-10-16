WITH source_dates AS (
SELECT CAST(at_timezone(order_date,current_timezone()) AS DATE) AS d FROM lake.stg.pg_public_order WHERE batch_id = '{{batch_id}}' AND order_date IS NOT NULL
UNION
SELECT CAST(at_timezone(delivery_date,current_timezone()) AS DATE) AS d FROM lake.stg.pg_public_order WHERE batch_id = '{{batch_id}}' AND delivery_date IS NOT NULL
UNION
SELECT CAST(at_timezone(order_date,current_timezone()) AS DATE) AS d FROM lake.stg.mongo_orders WHERE batch_id = '{{batch_id}}' AND order_date IS NOT NULL
UNION
SELECT CAST(at_timezone(date_time,current_timezone()) AS DATE) AS d FROM lake.stg.pg_external_order_statuses WHERE batch_id = '{{batch_id}}' AND date_time IS NOT NULL
UNION
SELECT CAST(at_timezone(date_time,current_timezone()) AS DATE) AS d FROM lake.stg.pg_external_user_behavior WHERE batch_id = '{{batch_id}}' AND date_time IS NOT NULL
UNION
SELECT CAST(date_parse(CAST(date_id AS VARCHAR),'%Y%m%d') AS DATE) AS d FROM lake.stg.pg_external_marketing_research WHERE batch_id = '{{batch_id}}'
), bounds AS (SELECT min(d) AS first_day,max(d) AS last_day FROM source_dates)
SELECT CAST(format_datetime(CAST(d AS TIMESTAMP),'yyyyMMdd') AS INTEGER) AS date_key, d AS date_value, year(d) AS year, quarter(d) AS quarter, month(d) AS month, day(d) AS day FROM bounds CROSS JOIN UNNEST(sequence(first_day,last_day)) AS dates(d)
