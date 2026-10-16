SELECT d.date_value AS report_date, r.restaurant_id, r.name AS restaurant_name,
       count(*) AS orders_count, CAST(sum(o.cost) AS DECIMAL(38,2)) AS cost_total,
       CAST(sum(o.payment) AS DECIMAL(38,2)) AS payment_total,
       CAST(sum(o.bonus_for_visit) AS DECIMAL(38,2)) AS bonus_for_visit_total
FROM lake.dds.fact_restaurant_orders o
JOIN lake.dds.dim_date d ON d.date_key=o.date_key
JOIN lake.dds.dim_restaurant r ON r.restaurant_key=o.restaurant_key
WHERE o.status_code='closed'
GROUP BY d.date_value, r.restaurant_id, r.name
ORDER BY report_date, restaurant_id
