from alembic import op

from warehouse.config import Settings

revision = 's003'
down_revision = 's002'

BUSINESS_TABLES = (
    'public.master',
    'public.product',
    'public.master_product',
    'public.client',
    'public."order"',
    'external_source.order_statuses',
    'external_source.user_behavior',
    'external_source.marketing_research',
)


def upgrade():
    settings = Settings.from_env()
    reader = op.get_bind().dialect.identifier_preparer.quote(
        settings.get('SOURCE_ETL_USER')
    )
    op.execute(f"REVOKE SELECT ON {', '.join(BUSINESS_TABLES)} FROM {reader}")
    op.execute(f'GRANT SELECT ON public.logs TO {reader}')


def downgrade():
    settings = Settings.from_env()
    reader = op.get_bind().dialect.identifier_preparer.quote(
        settings.get('SOURCE_ETL_USER')
    )
    op.execute(f"GRANT SELECT ON {', '.join(BUSINESS_TABLES)} TO {reader}")
