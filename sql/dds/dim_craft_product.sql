SELECT 'craft:product:' || CAST(product_id AS VARCHAR) AS product_key, product_id, name, description, type AS product_type FROM lake.stg.pg_public_product WHERE batch_id = '{{batch_id}}'
