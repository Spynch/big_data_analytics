"""Explicit extension: email, original order price and independent full payment."""
from alembic import op

revision = "pg_0002"
down_revision = "pg_0001"


def upgrade():
    op.execute('''
ALTER TABLE public.client ADD COLUMN email TEXT;
ALTER TABLE public."order" ADD COLUMN order_price NUMERIC(18,2);
ALTER TABLE public."order" ADD COLUMN paid_at TIMESTAMPTZ;
ALTER TABLE public."order" ADD CONSTRAINT order_price_positive CHECK (order_price >= 0);
COMMENT ON COLUMN public."order".order_price IS
  'Historical price snapshot. Legacy NULL requires explicit verified backfill; ETL rejects NULL.';
CREATE FUNCTION public.capture_order_price() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.order_price IS NULL THEN
    SELECT price INTO NEW.order_price FROM public.master_product
    WHERE master_id = NEW.master_id AND product_id = NEW.product_id;
  END IF;
  IF NEW.order_price IS NULL THEN
    RAISE EXCEPTION 'Missing offer price for master %, product %', NEW.master_id, NEW.product_id;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER capture_order_price BEFORE INSERT ON public."order"
FOR EACH ROW EXECUTE FUNCTION public.capture_order_price();
''')


def downgrade():
    raise RuntimeError("Price/payment history must not be silently discarded")
