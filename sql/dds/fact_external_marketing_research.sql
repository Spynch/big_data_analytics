SELECT id,date_id AS date_key,sales_qty,sales_amt FROM lake.stg.pg_external_marketing_research WHERE batch_id = '{{batch_id}}'
