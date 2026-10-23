$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
& "$PSScriptRoot/init-env.ps1"
$project = 'warehouse-test-' + [Guid]::NewGuid().ToString('N').Substring(0, 12)
$composeArgs = @('compose', '-p', $project, '-f', 'compose.yaml', '-f', 'compose.test.yaml')

function Compose {
    & docker @composeArgs @args
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed: $args" }
}

try {
    Compose build migrate
    Compose up -d --wait postgres-source postgres-dwh mongo-source
    Compose run --rm -e WAREHOUSE_TEST_MODE=1 smoke-test python -m unittest discover -s tests/integration -v
} finally {
    & docker @composeArgs down --volumes --remove-orphans
}
