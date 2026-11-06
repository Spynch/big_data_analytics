CREATE TABLE dds.dim_date (
    date_key INTEGER PRIMARY KEY, date_value DATE NOT NULL UNIQUE,
    year INTEGER NOT NULL, quarter INTEGER NOT NULL, month INTEGER NOT NULL, day INTEGER NOT NULL,
    CHECK (date_key = to_char(date_value, 'YYYYMMDD')::integer)
);
CREATE TABLE dds.dim_craft_client (
    client_key BIGINT PRIMARY KEY, client_id BIGINT NOT NULL UNIQUE,
    name TEXT NOT NULL, phone TEXT, address TEXT, birthday DATE, email TEXT,
    CHECK (client_key = client_id)
);
CREATE TABLE dds.dim_craft_master (
    master_key BIGINT PRIMARY KEY, master_id BIGINT NOT NULL UNIQUE,
    name TEXT NOT NULL, phone TEXT, address TEXT, birthday DATE,
    CHECK (master_key = master_id)
);
CREATE TABLE dds.dim_craft_product (
    product_key BIGINT PRIMARY KEY, product_id BIGINT NOT NULL UNIQUE,
    name TEXT NOT NULL, description TEXT, product_type TEXT,
    CHECK (product_key = product_id)
);
CREATE TABLE dds.dim_craft_order_status (
    status_code TEXT PRIMARY KEY CHECK (status_code IN ('created', 'in_progress', 'delivery', 'done', 'cancelled'))
);
CREATE TABLE dds.dim_restaurant_client (
    client_key BIGINT PRIMARY KEY, client_id BIGINT NOT NULL UNIQUE, source_object_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL, phone TEXT, email TEXT, birthday DATE, login TEXT, address JSONB,
    CHECK (client_key = client_id)
);
CREATE TABLE dds.dim_restaurant (
    restaurant_key BIGINT PRIMARY KEY, restaurant_id BIGINT NOT NULL UNIQUE,
    source_object_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL, phone TEXT, email TEXT,
    founding_day DATE, address TEXT, CHECK (restaurant_key = restaurant_id)
);
CREATE TABLE dds.dim_restaurant_order_status (
    status_code TEXT PRIMARY KEY CHECK (status_code <> '')
);
CREATE TABLE dds.fact_craft_offers (
    id BIGINT PRIMARY KEY,
    master_key BIGINT NOT NULL REFERENCES dds.dim_craft_master,
    product_key BIGINT NOT NULL REFERENCES dds.dim_craft_product,
    price NUMERIC(18,2) NOT NULL CHECK (price >= 0), UNIQUE (master_key, product_key)
);
CREATE TABLE dds.fact_craft_orders (
    order_id BIGINT PRIMARY KEY,
    client_key BIGINT NOT NULL REFERENCES dds.dim_craft_client,
    master_key BIGINT NOT NULL REFERENCES dds.dim_craft_master,
    product_key BIGINT NOT NULL REFERENCES dds.dim_craft_product,
    status_code TEXT NOT NULL REFERENCES dds.dim_craft_order_status,
    created_date_key INTEGER NOT NULL REFERENCES dds.dim_date,
    delivery_date_key INTEGER REFERENCES dds.dim_date,
    order_date TIMESTAMPTZ NOT NULL, delivery_date TIMESTAMPTZ,
    order_price NUMERIC(18,2) NOT NULL CHECK (order_price >= 0), paid_at TIMESTAMPTZ,
    CHECK ((status_code = 'done' AND delivery_date IS NOT NULL AND delivery_date_key IS NOT NULL
            AND delivery_date >= order_date)
        OR (status_code <> 'done' AND delivery_date IS NULL AND delivery_date_key IS NULL))
);
CREATE TABLE dds.fact_restaurant_orders (
    order_id BIGINT PRIMARY KEY, source_object_id TEXT NOT NULL UNIQUE,
    date_key INTEGER NOT NULL REFERENCES dds.dim_date,
    client_key BIGINT NOT NULL REFERENCES dds.dim_restaurant_client,
    restaurant_key BIGINT NOT NULL REFERENCES dds.dim_restaurant,
    status_code TEXT NOT NULL REFERENCES dds.dim_restaurant_order_status,
    order_date TIMESTAMPTZ NOT NULL,
    cost NUMERIC(18,2) NOT NULL CHECK (cost >= 0),
    payment NUMERIC(18,2) NOT NULL CHECK (payment >= 0),
    payed_by_bonuses NUMERIC(18,2) NOT NULL CHECK (payed_by_bonuses >= 0),
    bonus_for_visit NUMERIC(18,2) NOT NULL CHECK (bonus_for_visit >= 0)
);
CREATE INDEX ON dds.fact_craft_orders (client_key, delivery_date);
CREATE INDEX ON dds.fact_craft_orders (client_key, order_date);
CREATE INDEX ON dds.fact_craft_orders (master_key);
CREATE INDEX ON dds.fact_craft_orders (product_key);
CREATE INDEX ON dds.fact_restaurant_orders (date_key, restaurant_key);
CREATE INDEX ON dds.fact_restaurant_orders (client_key);
