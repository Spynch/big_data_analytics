from pathlib import Path
from alembic import op
from warehouse.config import Settings

revision = 'w001'
down_revision = None


def upgrade():
    for name in ('w001_stg.sql', 'w001_dds.sql', 'w001_json.sql'):
        op.execute(Path(__file__).with_name(name).read_text(encoding='utf-8'))
    settings = Settings.from_env()
    quote = op.get_bind().dialect.identifier_preparer.quote
    etl = quote(settings.get('DWH_ETL_USER'))
    op.execute(f'GRANT USAGE ON SCHEMA stg, dds, cdm TO {etl}')
    op.execute(f'GRANT SELECT, INSERT, DELETE ON ALL TABLES IN SCHEMA stg, dds TO {etl}')
    op.execute(f'REVOKE DELETE ON stg.pg_logs FROM {etl}')
    op.execute(f'GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA stg TO {etl}')


def downgrade():
    op.execute('DROP SCHEMA cdm, dds, stg CASCADE')
