$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $root '.env'
$existing = @{}
if (Test-Path -LiteralPath $envPath) {
    foreach ($line in Get-Content -LiteralPath $envPath) {
        if ($line -match '^([A-Z_][A-Z_0-9]*)=(.*)$') { $existing[$matches[1]] = $matches[2] }
    }
}
$added = @()
foreach ($line in Get-Content -LiteralPath (Join-Path $root '.env.example')) {
    if ($line -notmatch '^([A-Z_][A-Z_0-9]*)=(.*)$') { continue }
    $key = $matches[1]
    $value = $matches[2]
    if ($existing.ContainsKey($key) -and $existing[$key]) { continue }
    if (-not $value) {
        $bytes = New-Object byte[] 32
        $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
        $rng.GetBytes($bytes)
        $rng.Dispose()
        if ($key -eq 'AIRFLOW_FERNET_KEY') {
            $value = [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_')
        } else {
            $value = -join ($bytes | ForEach-Object { $_.ToString('x2') })
        }
    }
    $added += "$key=$value"
}
if ($added.Count) {
    [IO.File]::AppendAllText($envPath, "`n" + ($added -join "`n") + "`n", (New-Object Text.UTF8Encoding $false))
}
Write-Host 'Local .env is ready; existing settings were preserved.'
