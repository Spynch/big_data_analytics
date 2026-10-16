param([ValidateSet('up','migrate','seed','demo','run','smoke','test','status','stop','down')][string]$Action = 'up')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
function Compose {
    & docker compose @args
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed with exit code $LASTEXITCODE" }
}
function Migrate {
    foreach ($job in @('meta-init','minio-init','lakekeeper-migrate','lakekeeper-init','postgres-migrate','mongo-migrate','control-migrate','lake-migrate','cdm-init','clickhouse-migrate','airflow-init')) {
        Compose run --rm --no-deps $job
    }
}
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
    Write-Host 'Created .env with local demo credentials.'
}
switch ($Action) {
    'up' {
        Compose config --quiet
        Compose build warehouse-cli mongo-migrate minio
        Compose up -d
        Compose up -d --no-deps --wait airflow-api-server airflow-scheduler airflow-dag-processor trino clickhouse
    }
    'migrate' { Migrate }
    'seed' { Compose run --rm --no-deps seed }
    'demo' { Compose run --rm --no-deps warehouse-cli demo }
    'run' { Compose run --rm --no-deps warehouse-cli trigger }
    'smoke' { Compose run --rm --no-deps smoke-test }
    'test' { Compose run --rm --no-deps warehouse-cli test }
    'status' { Compose ps -a; Compose run --rm --no-deps warehouse-cli status }
    'stop' { Compose stop }
    'down' { Compose down }
}
