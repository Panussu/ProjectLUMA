param(
    [int]$Days = 0,
    [switch]$Apply
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$serviceRoot = Join-Path $repoRoot "backend"
$pythonPath = Join-Path $serviceRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "backend/.venv is missing. Run scripts/run-backend.ps1 first."
}

$maintenanceArgs = @("maintenance.py", "cleanup")
if ($Days -gt 0) { $maintenanceArgs += @("--days", $Days) }
if ($Apply) { $maintenanceArgs += "--apply" }

Push-Location $serviceRoot
try {
    & $pythonPath @maintenanceArgs
    if ($LASTEXITCODE -ne 0) { throw "Backend cleanup failed." }
} finally {
    Pop-Location
}
