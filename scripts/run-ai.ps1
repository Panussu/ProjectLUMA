$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$serviceRoot = Join-Path $repoRoot "ai-engine"
$pythonPath = Join-Path $serviceRoot ".venv\Scripts\python.exe"
$pipPath = Join-Path $serviceRoot ".venv\Scripts\pip.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv (Join-Path $serviceRoot ".venv")
}

& $pipPath install -r (Join-Path $serviceRoot "requirements.txt") --disable-pip-version-check

if (-not (Test-Path -LiteralPath (Join-Path $serviceRoot ".env"))) {
    Copy-Item -LiteralPath (Join-Path $serviceRoot ".env.example") -Destination (Join-Path $serviceRoot ".env")
    Write-Host "Created ai-engine/.env from the example. Change its token before LAN deployment."
}

Push-Location $serviceRoot
try {
    & $pythonPath app.py
} finally {
    Pop-Location
}

