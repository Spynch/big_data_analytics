#!/usr/bin/env bash
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv reader SOURCE_ETL_USER
\getenv reader_password SOURCE_ETL_PASSWORD
\getenv app SOURCE_APP_USER
\getenv app_password SOURCE_APP_PASSWORD
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'reader', :'reader_password') \gexec
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app', :'app_password') \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL
