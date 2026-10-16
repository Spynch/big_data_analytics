"""Run state, dataset completeness, publication state and lake migration ledger."""
from alembic import op

revision = "control_0001"
down_revision = None


def upgrade():
    op.execute('''
CREATE TABLE batches (
  batch_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(), finished_at TIMESTAMPTZ,
  error TEXT
);
CREATE TABLE dataset_loads (
  batch_id TEXT NOT NULL REFERENCES batches, dataset TEXT NOT NULL,
  row_count BIGINT NOT NULL, snapshot_id BIGINT, extracted_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY(batch_id,dataset)
);
CREATE TABLE publications (
  batch_id TEXT NOT NULL REFERENCES batches, mart TEXT NOT NULL,
  status TEXT NOT NULL, row_count BIGINT NOT NULL, content_sha256 TEXT NOT NULL,
  object_etag TEXT, published_at TIMESTAMPTZ,
  PRIMARY KEY(batch_id,mart)
);
CREATE TABLE lake_migrations (
  version TEXT PRIMARY KEY, checksum TEXT NOT NULL, status TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(), completed_at TIMESTAMPTZ,
  error TEXT
);
''')


def downgrade():
    raise RuntimeError("Run and migration history must be retained")
