from pathlib import Path
from alembic import op

revision = 's002'
down_revision = 's001'


def upgrade():
    op.execute(Path(__file__).with_suffix('.sql').read_text(encoding='utf-8'))


def downgrade():
    op.execute('DROP TRIGGER snapshot_order_price ON public."order"')
    op.execute('DROP FUNCTION public.snapshot_order_price()')
    op.execute('ALTER TABLE public."order" DROP COLUMN paid_at, DROP COLUMN order_price')
    op.execute('ALTER TABLE public.client DROP COLUMN email')
