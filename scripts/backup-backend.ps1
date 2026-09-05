param(
    [string]$Destination
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$serviceRoot = Join-Path $repoRoot "backend"
$pythonPath = Join-Path $serviceRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "backend/.venv is missing. Run scripts/run-backend.ps1 first."
}

$maintenanceArgs = @("maintenance.py", "backup")
if ($Destination) {
    $maintenanceArgs += @("--destination", $Destination)
}

Push-Location $serviceRoot
try {
    & $pythonPath @maintenanceArgs
    if ($LASTEXITCODE -ne 0) { throw "Backend backup failed." }
} finally {
    Pop-Location
}
