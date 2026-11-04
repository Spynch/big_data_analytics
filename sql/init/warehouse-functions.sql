CREATE FUNCTION stg.bson_text(value JSONB) RETURNS TEXT
LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT coalesce(value->>'$numberInt', value->>'$numberLong',
        value->>'$numberDecimal', value #>> '{}');
$$;

CREATE FUNCTION stg.source_timestamp(value JSONB, source_zone TEXT) RETURNS TIMESTAMPTZ
LANGUAGE plpgsql STABLE STRICT AS $$
DECLARE raw TEXT; local_time TIMESTAMP;
BEGIN
    IF value = 'null'::jsonb THEN
        RETURN NULL;
    END IF;
    IF value ? '$date' THEN
        RETURN TIMESTAMPTZ 'epoch' + (value #>> '{$date,$numberLong}')::numeric / 1000 * INTERVAL '1 second';
    END IF;
    raw := value #>> '{}';
    IF raw ~ '^\d{2}\.\d{2}\.\d{4}( \d{2}:\d{2}:\d{2})?$' THEN
        local_time := (substring(raw, 7, 4) || '-' || substring(raw, 4, 2) || '-' ||
            substring(raw, 1, 2) || coalesce(nullif(substring(raw, 11), ''), ' 00:00:00'))::timestamp;
        RETURN local_time AT TIME ZONE source_zone;
    ELSIF raw ~ '^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$' THEN
        IF raw ~ '(Z|[+-]\d{2}:?\d{2})$' THEN
            RETURN raw::timestamptz;
        END IF;
        RETURN raw::timestamp AT TIME ZONE source_zone;
    END IF;
    RAISE EXCEPTION 'Invalid source date: % (expected BSON Date, ISO 8601 or dd.mm.yyyy [hh:mm:ss])', raw;
END;
$$;

CREATE FUNCTION stg.source_date(value JSONB) RETURNS DATE
LANGUAGE plpgsql STABLE STRICT AS $$
DECLARE raw TEXT := value #>> '{}';
BEGIN
    IF jsonb_typeof(value) = 'string' AND raw ~ '^\d{4}-\d{2}-\d{2}' THEN
        PERFORM stg.source_timestamp(value, 'UTC');
        RETURN substring(raw, 1, 10)::date;
    END IF;
    RETURN (stg.source_timestamp(value, 'UTC') AT TIME ZONE 'UTC')::date;
END;
$$;

CREATE FUNCTION stg.marketing_date(value INTEGER) RETURNS DATE
LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE raw TEXT := value::text;
BEGIN
    IF raw !~ '^\d{8}$' THEN
        RAISE EXCEPTION 'Invalid marketing date_id: % (expected YYYYMMDD)', value;
    END IF;
    RETURN make_date(substring(raw, 1, 4)::integer, substring(raw, 5, 2)::integer,
        substring(raw, 7, 2)::integer);
END;
$$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA stg FROM PUBLIC;
