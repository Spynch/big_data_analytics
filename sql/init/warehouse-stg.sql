CREATE SCHEMA stg;
CREATE SCHEMA dds;
CREATE SCHEMA cdm;

CREATE TABLE stg.pg_public_master (
    master_id BIGINT PRIMARY KEY, name TEXT, phone TEXT, address TEXT, birthday DATE,
    extracted_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE stg.pg_public_product (
    product_id BIGINT PRIMARY KEY, name TEXT, description TEXT, type TEXT,
    extracted_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE stg.pg_public_master_product (
    id BIGINT PRIMARY KEY, master_id BIGINT, product_id BIGINT, price NUMERIC(18,2),
    extracted_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE stg.pg_public_client (
    client_id BIGINT PRIMARY KEY, name TEXT, phone TEXT, address TEXT, birthday DATE, email TEXT,
    extracted_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE stg.pg_public_order (
    order_id BIGINT PRIMARY KEY, master_id BIGINT, product_id BIGINT, client_id BIGINT,
    order_date TIMESTAMPTZ, delivery_date TIMESTAMPTZ, status TEXT,
    order_price NUMERIC(18,2), paid_at TIMESTAMPTZ, extracted_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE stg.pg_external_order_statuses (
    id BIGINT PRIMARY KEY, date_time TIMESTAMPTZ, client_id BIGINT,
    quantity BIGINT, payment_amount NUMERIC(18,2), extracted_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE stg.pg_external_user_behavior (
    id BIGINT PRIMARY KEY, date_time TIMESTAMPTZ, client_id BIGINT, extracted_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE stg.pg_external_marketing_research (
    id BIGINT PRIMARY KEY, date_id INTEGER, sales_qty BIGINT, sales_amt NUMERIC(18,2),
    extracted_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE stg.pg_logs (
    id BIGINT PRIMARY KEY, changed_at TIMESTAMPTZ, object_schema TEXT, object_type TEXT,
    operation TEXT, object_value JSONB, extracted_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE stg.mongo_clients (
    source_id TEXT PRIMARY KEY, payload JSONB NOT NULL, extracted_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE stg.mongo_orders (
    source_id TEXT PRIMARY KEY, payload JSONB NOT NULL, extracted_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE stg.mongo_restaurant (
    source_id TEXT PRIMARY KEY, payload JSONB NOT NULL, extracted_at TIMESTAMPTZ NOT NULL
);
