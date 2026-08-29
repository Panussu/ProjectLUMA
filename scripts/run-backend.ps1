$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$serviceRoot = Join-Path $repoRoot "backend"
$pythonPath = Join-Path $serviceRoot ".venv\Scripts\python.exe"
$pipPath = Join-Path $serviceRoot ".venv\Scripts\pip.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv (Join-Path $serviceRoot ".venv")
}

& $pipPath install -r (Join-Path $serviceRoot "requirements.txt") --disable-pip-version-check

if (-not (Test-Path -LiteralPath (Join-Path $serviceRoot ".env"))) {
    Copy-Item -LiteralPath (Join-Path $serviceRoot ".env.example") -Destination (Join-Path $serviceRoot ".env")
    Write-Host "Created backend/.env from the example. Change its secrets before LAN deployment."
}

Push-Location $serviceRoot
try {
    & $pythonPath run.py
} finally {
    Pop-Location
}

