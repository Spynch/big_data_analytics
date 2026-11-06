CREATE SCHEMA external_source;

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
