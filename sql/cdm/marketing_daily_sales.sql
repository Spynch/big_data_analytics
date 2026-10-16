SELECT d.date_value AS report_date, sum(f.sales_qty) AS sales_qty,
       CAST(sum(f.sales_amt) AS DECIMAL(38,2)) AS sales_amt
FROM lake.dds.fact_external_marketing_research f JOIN lake.dds.dim_date d ON d.date_key=f.date_key
GROUP BY d.date_value ORDER BY report_date
