from pathlib import Path
from alembic import op
from warehouse.config import Settings

revision = 'w002'
down_revision = 'w001'


def upgrade():
    op.execute(Path(__file__).with_suffix('.sql').read_text(encoding='utf-8'))
    settings = Settings.from_env()
    quote = op.get_bind().dialect.identifier_preparer.quote
    for key in ('REPORT_USER', 'DWH_ETL_USER'):
        user = quote(settings.get(key))
        op.execute(f'GRANT USAGE ON SCHEMA cdm TO {user}')
        op.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA cdm TO {user}')


def downgrade():
    op.execute('DROP VIEW cdm.craft_customer_monthly, cdm.restaurant_daily_sales, '
               'cdm.external_client_activity_daily, cdm.marketing_daily_sales, cdm.external_order_statuses_daily')
