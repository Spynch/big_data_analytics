from pathlib import Path

from alembic import op

revision = 'w003'
down_revision = 'w002'


def upgrade():
    op.execute(Path(__file__).with_suffix('.sql').read_text(encoding='utf-8'))


def downgrade():
    path = Path(__file__).with_name('w003_order_count_down.sql')
    op.execute(path.read_text(encoding='utf-8'))
