CREATE FUNCTION stg.bson_text(value JSONB) RETURNS TEXT
LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT coalesce(
        value->>'$numberInt',
        value->>'$numberLong',
        value->>'$numberDecimal',
        value #>> '{}'
    );
$$;

CREATE FUNCTION stg.source_timestamp(value JSONB) RETURNS TIMESTAMPTZ
LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT TIMESTAMPTZ 'epoch'
        + (value #>> '{$date,$numberLong}')::numeric / 1000 * INTERVAL '1 second';
$$;

CREATE FUNCTION stg.source_date(value JSONB) RETURNS DATE
LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT (stg.source_timestamp(value) AT TIME ZONE 'UTC')::date;
$$;
