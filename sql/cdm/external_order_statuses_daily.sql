SELECT d.date_value AS report_date, c.client_id, sum(f.quantity) AS quantity_total,
       CAST(sum(f.payment_amount) AS DECIMAL(38,2)) AS payment_amount_total
FROM lake.dds.fact_external_order_statuses f
JOIN lake.dds.dim_date d ON d.date_key=f.date_key
JOIN lake.dds.dim_external_client c ON c.client_key=f.client_key
GROUP BY d.date_value, c.client_id ORDER BY report_date, client_id
