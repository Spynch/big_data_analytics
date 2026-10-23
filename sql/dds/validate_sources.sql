DO $$
DECLARE invalid RECORD;
BEGIN
    SELECT order_id, status INTO invalid FROM stg.pg_public_order
    WHERE replace(status, ' ', '_') NOT IN ('created', 'in_progress', 'delivery', 'done', 'cancelled')
        OR status IS NULL LIMIT 1;
    IF FOUND THEN
        RAISE EXCEPTION 'Unknown craft status, order %: %', invalid.order_id, invalid.status;
    END IF;

    SELECT o.payload->'order_id' AS order_id INTO invalid
    FROM stg.mongo_orders o
    LEFT JOIN stg.mongo_clients c ON stg.bson_text(c.payload->'client_id')::bigint = stg.bson_text(o.payload->'client_id')::bigint
    LEFT JOIN stg.mongo_restaurant r ON stg.bson_text(r.payload->'restaurant_id')::bigint = stg.bson_text(o.payload->'restaurant_id')::bigint
    WHERE c.source_id IS NULL OR r.source_id IS NULL LIMIT 1;
    IF FOUND THEN
        RAISE EXCEPTION 'MongoDB order % references a missing client or restaurant', invalid.order_id;
    END IF;
    PERFORM stg.source_timestamp(payload->'update_time', current_setting('warehouse.source_timezone'))
    FROM stg.mongo_clients WHERE payload ? 'update_time';
    PERFORM stg.source_timestamp(payload->'update_time', current_setting('warehouse.source_timezone'))
    FROM stg.mongo_orders WHERE payload ? 'update_time';
END;
$$;
