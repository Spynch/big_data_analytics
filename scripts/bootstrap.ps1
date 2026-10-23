$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
& "$PSScriptRoot/init-env.ps1"

function Compose {
    & docker compose @args
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed: $args" }
}

Compose build migrate
Compose up -d --wait postgres-source postgres-dwh mongo-source
Compose run --rm migrate
Compose run --rm seed
Compose run --rm airflow-init
Compose up -d --wait airflow-api-server airflow-scheduler airflow-dag-processor
Compose run --rm smoke-test python -m airflow_utils.run_dag
Compose run --rm smoke-test
Write-Host 'Bootstrap completed. Airflow is available on the configured AIRFLOW_PORT.'
