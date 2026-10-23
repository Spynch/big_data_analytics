from pathlib import Path
from alembic import op
from warehouse.config import Settings

revision = 's001'
down_revision = None


def upgrade():
    op.execute(Path(__file__).with_suffix('.sql').read_text(encoding='utf-8'))
    settings = Settings.from_env()
    quote = op.get_bind().dialect.identifier_preparer.quote
    reader = quote(settings.get('SOURCE_ETL_USER'))
    app = quote(settings.get('SOURCE_APP_USER'))
    op.execute(f'GRANT USAGE ON SCHEMA public, external_source TO {reader}, {app}')
    op.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA public, external_source TO {reader}, {app}')
    for table in ('public.master', 'public.product', 'public.master_product',
                  'public.client', 'public."order"', 'external_source.order_statuses',
                  'external_source.user_behavior', 'external_source.marketing_research'):
        op.execute(f'GRANT INSERT, UPDATE, DELETE, TRUNCATE ON {table} TO {app}')


def downgrade():
    op.execute('DROP SCHEMA external_source CASCADE')
    op.execute('DROP TABLE public."order", public.master_product, public.client, public.product, public.master, public.logs CASCADE')
    op.execute('DROP FUNCTION public.audit_row(), public.audit_truncate()')
