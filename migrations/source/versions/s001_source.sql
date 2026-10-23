CREATE SCHEMA external_source;

CREATE TABLE public.master (
    master_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    address TEXT,
    birthday DATE
);
CREATE TABLE public.product (
    product_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    type TEXT
);
CREATE TABLE public.master_product (
    id BIGINT PRIMARY KEY,
    master_id BIGINT NOT NULL REFERENCES public.master,
    product_id BIGINT NOT NULL REFERENCES public.product,
    price NUMERIC(18,2) NOT NULL CHECK (price >= 0),
    UNIQUE (master_id, product_id)
);
CREATE TABLE public.client (
    client_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    address TEXT,
    birthday DATE
);
CREATE TABLE public."order" (
    order_id BIGINT PRIMARY KEY,
    master_id BIGINT NOT NULL REFERENCES public.master,
    product_id BIGINT NOT NULL REFERENCES public.product,
    client_id BIGINT NOT NULL REFERENCES public.client,
    order_date TIMESTAMPTZ NOT NULL,
    delivery_date TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('created', 'in_progress', 'in progress', 'delivery', 'done', 'cancelled')),
    FOREIGN KEY (master_id, product_id) REFERENCES public.master_product (master_id, product_id),
    CHECK ((status = 'done' AND delivery_date IS NOT NULL AND delivery_date >= order_date)
        OR (status <> 'done' AND delivery_date IS NULL))
);
CREATE TABLE external_source.order_statuses (
    id BIGINT PRIMARY KEY,
    date_time TIMESTAMPTZ NOT NULL,
    client_id BIGINT NOT NULL,
    quantity BIGINT NOT NULL CHECK (quantity >= 0),
    payment_amount NUMERIC(18,2) NOT NULL CHECK (payment_amount >= 0)
);
CREATE TABLE external_source.user_behavior (
    id BIGINT PRIMARY KEY,
    date_time TIMESTAMPTZ NOT NULL,
    client_id BIGINT NOT NULL
);
CREATE TABLE external_source.marketing_research (
    id BIGINT PRIMARY KEY,
    date_id INTEGER NOT NULL,
    sales_qty BIGINT NOT NULL CHECK (sales_qty >= 0),
    sales_amt NUMERIC(18,2) NOT NULL CHECK (sales_amt >= 0)
);
CREATE TABLE public.logs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    object_schema TEXT NOT NULL,
    object_type TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE')),
    object_value JSONB NOT NULL
);

CREATE FUNCTION public.audit_row() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    INSERT INTO public.logs (object_schema, object_type, operation, object_value)
    VALUES (TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_OP,
        CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END);
    RETURN NULL;
END;
$$;

CREATE FUNCTION public.audit_truncate() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    EXECUTE format(
        'INSERT INTO public.logs (object_schema, object_type, operation, object_value)
         SELECT %L, %L, ''TRUNCATE'', to_jsonb(t) FROM %I.%I AS t',
        TG_TABLE_SCHEMA, TG_TABLE_NAME, TG_TABLE_SCHEMA, TG_TABLE_NAME);
    RETURN NULL;
END;
$$;
REVOKE ALL ON FUNCTION public.audit_row(), public.audit_truncate() FROM PUBLIC;

DO $$
DECLARE item RECORD;
BEGIN
    FOR item IN SELECT * FROM (VALUES
        ('public', 'master'), ('public', 'product'), ('public', 'master_product'),
        ('public', 'client'), ('public', 'order'),
        ('external_source', 'order_statuses'), ('external_source', 'user_behavior'),
        ('external_source', 'marketing_research')
    ) AS tables(schema_name, table_name)
    LOOP
        EXECUTE format('CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON %I.%I
            FOR EACH ROW EXECUTE FUNCTION public.audit_row()', item.schema_name, item.table_name);
        EXECUTE format('CREATE TRIGGER audit_truncate BEFORE TRUNCATE ON %I.%I
            FOR EACH STATEMENT EXECUTE FUNCTION public.audit_truncate()', item.schema_name, item.table_name);
    END LOOP;
END;
$$;
