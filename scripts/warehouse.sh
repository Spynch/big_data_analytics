#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  cp .env.example .env
  echo 'Created .env with local demo credentials.'
fi
case "${1:-up}" in
  up)
    docker compose config --quiet
    docker compose build warehouse-cli mongo-migrate minio
    docker compose up -d
    docker compose up -d --no-deps --wait airflow-api-server airflow-scheduler airflow-dag-processor trino clickhouse
    ;;
  migrate)
    for job in meta-init minio-init lakekeeper-migrate lakekeeper-init postgres-migrate mongo-migrate control-migrate lake-migrate cdm-init clickhouse-migrate airflow-init; do
      docker compose run --rm --no-deps "$job"
    done
    ;;
  seed) docker compose run --rm --no-deps seed ;;
  demo) docker compose run --rm --no-deps warehouse-cli demo ;;
  run) docker compose run --rm --no-deps warehouse-cli trigger ;;
  smoke) docker compose run --rm --no-deps smoke-test ;;
  test) docker compose run --rm --no-deps warehouse-cli test ;;
  status) docker compose ps -a; docker compose run --rm --no-deps warehouse-cli status ;;
  stop) docker compose stop ;;
  down) docker compose down ;;
  *) echo 'Usage: sh scripts/warehouse.sh up|migrate|seed|demo|run|smoke|test|status|stop|down' >&2; exit 2 ;;
esac
