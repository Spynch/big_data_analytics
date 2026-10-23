#!/usr/bin/env bash
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv etl DWH_ETL_USER
\getenv etl_password DWH_ETL_PASSWORD
\getenv reader REPORT_USER
\getenv reader_password REPORT_PASSWORD
\getenv airflow AIRFLOW_DB_USER
\getenv airflow_password AIRFLOW_DB_PASSWORD
\getenv airflow_db AIRFLOW_DB
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'etl', :'etl_password') \gexec
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'reader', :'reader_password') \gexec
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'airflow', :'airflow_password') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'airflow_db', :'airflow') \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'airflow_db') \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL
