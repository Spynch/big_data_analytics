SELECT 'craft:client:' || CAST(client_id AS VARCHAR) AS client_key, client_id, name, phone, address, birthday, email FROM lake.stg.pg_public_client WHERE batch_id = '{{batch_id}}'
