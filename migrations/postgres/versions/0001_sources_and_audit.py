"""Original craft model, external CSV schema and transactional row audit."""
from alembic import op

revision = "pg_0001"
down_revision = None


def upgrade():
    op.execute('''
CREATE SCHEMA external_source;
CREATE TABLE public.master (
  master_id BIGINT PRIMARY KEY, name TEXT NOT NULL, phone TEXT, address TEXT, birthday DATE
);
CREATE TABLE public.product (
  product_id BIGINT PRIMARY KEY, name TEXT NOT NULL, description TEXT, type TEXT
);
CREATE TABLE public.master_product (
  id BIGINT PRIMARY KEY, master_id BIGINT NOT NULL REFERENCES public.master,
  product_id BIGINT NOT NULL REFERENCES public.product,
  price NUMERIC(18,2) NOT NULL CHECK (price >= 0), UNIQUE(master_id, product_id)
);
CREATE TABLE public.client (
  client_id BIGINT PRIMARY KEY, name TEXT NOT NULL, phone TEXT, address TEXT, birthday DATE
);
CREATE TABLE public."order" (
  order_id BIGINT PRIMARY KEY,
  master_id BIGINT NOT NULL REFERENCES public.master,
  product_id BIGINT NOT NULL REFERENCES public.product,
  client_id BIGINT NOT NULL REFERENCES public.client,
  order_date TIMESTAMPTZ NOT NULL, delivery_date TIMESTAMPTZ,
  status TEXT NOT NULL CHECK (status IN ('created','in_progress','delivery','done','cancelled')),
  FOREIGN KEY(master_id, product_id) REFERENCES public.master_product(master_id, product_id),
  CHECK ((status = 'done' AND delivery_date IS NOT NULL AND delivery_date >= order_date)
      OR (status <> 'done' AND delivery_date IS NULL))
);
CREATE INDEX order_client_created ON public."order"(client_id, order_date);
CREATE INDEX order_delivered ON public."order"(delivery_date) WHERE status='done';
CREATE TABLE external_source.order_statuses (
  id BIGINT PRIMARY KEY, date_time TIMESTAMPTZ NOT NULL, client_id BIGINT NOT NULL,
  quantity BIGINT NOT NULL, payment_amount NUMERIC(18,2) NOT NULL
);
CREATE TABLE external_source.user_behavior (
  id BIGINT PRIMARY KEY, date_time TIMESTAMPTZ NOT NULL, client_id BIGINT NOT NULL
);
CREATE TABLE external_source.marketing_research (
  id BIGINT PRIMARY KEY, date_id INTEGER NOT NULL, sales_qty BIGINT NOT NULL,
  sales_amt NUMERIC(18,2) NOT NULL
);
CREATE TABLE public.logs (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  changed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  object_schema TEXT NOT NULL, object_type TEXT NOT NULL,
  object_value JSONB NOT NULL,
  operation TEXT NOT NULL CHECK (operation IN ('INSERT','UPDATE','DELETE','TRUNCATE'))
);
CREATE INDEX logs_object ON public.logs(object_schema, object_type, id);
CREATE FUNCTION public.audit_row() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  INSERT INTO public.logs(object_schema, object_type, object_value, operation)
  VALUES(TG_TABLE_SCHEMA, TG_TABLE_NAME,
         CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END, TG_OP);
  RETURN NULL;
END $$;
CREATE FUNCTION public.audit_truncate() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  EXECUTE format('INSERT INTO public.logs(object_schema,object_type,object_value,operation)
    SELECT %L,%L,to_jsonb(t),%L FROM %I.%I t',
    TG_TABLE_SCHEMA,TG_TABLE_NAME,'TRUNCATE',TG_TABLE_SCHEMA,TG_TABLE_NAME);
  RETURN NULL;
END $$;
''')
    for schema, table in [("public", t) for t in ["master", "product", "master_product", "client", "order"]] + [
        ("external_source", t) for t in ["order_statuses", "user_behavior", "marketing_research"]
    ]:
        op.execute(f'CREATE TRIGGER audit_row AFTER INSERT OR UPDATE OR DELETE ON "{schema}"."{table}" '
                   'FOR EACH ROW EXECUTE FUNCTION public.audit_row()')
        op.execute(f'CREATE TRIGGER audit_truncate BEFORE TRUNCATE ON "{schema}"."{table}" '
                   'FOR EACH STATEMENT EXECUTE FUNCTION public.audit_truncate()')


def downgrade():
    raise RuntimeError("Destructive source downgrade is intentionally unsupported; restore a backup instead")
