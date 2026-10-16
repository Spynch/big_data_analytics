SELECT DISTINCT final_status AS status_code FROM lake.stg.mongo_orders WHERE batch_id = '{{batch_id}}'
