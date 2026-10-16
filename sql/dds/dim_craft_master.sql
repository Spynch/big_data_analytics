SELECT 'craft:master:' || CAST(master_id AS VARCHAR) AS master_key, master_id, name, phone, address, birthday FROM lake.stg.pg_public_master WHERE batch_id = '{{batch_id}}'
