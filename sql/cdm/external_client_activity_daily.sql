WITH behavior AS (
    SELECT date_key, client_key, sum(event_count) AS event_count
    FROM lake.dds.fact_external_user_behavior GROUP BY date_key, client_key
), statuses AS (
    SELECT date_key, client_key, sum(quantity) AS quantity,
           CAST(sum(payment_amount) AS DECIMAL(38,2)) AS payment_amount
    FROM lake.dds.fact_external_order_statuses GROUP BY date_key, client_key
), joined AS (
    SELECT coalesce(b.date_key,s.date_key) AS date_key, coalesce(b.client_key,s.client_key) AS client_key,
           coalesce(b.event_count,BIGINT '0') AS behavior_events_count,
           coalesce(s.quantity,BIGINT '0') AS quantity_total,
           coalesce(s.payment_amount,DECIMAL '0.00') AS payment_amount_total
    FROM behavior b FULL OUTER JOIN statuses s ON b.date_key=s.date_key AND b.client_key=s.client_key
)
SELECT d.date_value AS report_date, c.client_id, j.behavior_events_count, j.quantity_total, j.payment_amount_total
FROM joined j JOIN lake.dds.dim_date d ON d.date_key=j.date_key
JOIN lake.dds.dim_external_client c ON c.client_key=j.client_key
ORDER BY report_date, client_id
