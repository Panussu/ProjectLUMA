param(
    [switch]$Vlan
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$serviceRoot = Join-Path $repoRoot "backend"
$pythonPath = Join-Path $serviceRoot ".venv\Scripts\python.exe"
$pipPath = Join-Path $serviceRoot ".venv\Scripts\pip.exe"
$environmentPath = Join-Path $serviceRoot ".env"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv (Join-Path $serviceRoot ".venv")
}

& $pipPath install -r (Join-Path $serviceRoot "requirements.txt") --disable-pip-version-check

if (-not (Test-Path -LiteralPath $environmentPath)) {
    $templateName = if ($Vlan) { ".env.vlan.example" } else { ".env.example" }
    Copy-Item -LiteralPath (Join-Path $serviceRoot $templateName) -Destination $environmentPath
    Write-Host "Created backend/.env from $templateName. Edit its secrets and addresses before starting."
    if ($Vlan) {
        throw "VLAN configuration contains placeholders. Edit backend/.env, then run this command again."
    }
}

Push-Location $serviceRoot
try {
    & $pythonPath run.py
} finally {
    Pop-Location
}
