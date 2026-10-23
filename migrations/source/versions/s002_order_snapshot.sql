ALTER TABLE public.client ADD COLUMN email TEXT;
ALTER TABLE public."order" ADD COLUMN order_price NUMERIC(18,2);
ALTER TABLE public."order" ADD COLUMN paid_at TIMESTAMPTZ;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM public."order" WHERE order_price IS NULL) THEN
        RAISE EXCEPTION 'Historical order prices are missing. Restore verified historical prices before migrating; current offer prices are not historical prices.';
    END IF;
END;
$$;
ALTER TABLE public."order" ALTER COLUMN order_price SET NOT NULL;
ALTER TABLE public."order" ADD CHECK (order_price >= 0);

CREATE FUNCTION public.snapshot_order_price() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
    SELECT price INTO NEW.order_price FROM public.master_product
    WHERE master_id = NEW.master_id AND product_id = NEW.product_id;
    IF NEW.order_price IS NULL THEN
        RAISE EXCEPTION 'No offer for master_id=%, product_id=%', NEW.master_id, NEW.product_id;
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER snapshot_order_price BEFORE INSERT ON public."order"
FOR EACH ROW EXECUTE FUNCTION public.snapshot_order_price();
