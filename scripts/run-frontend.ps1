$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot "frontend"

Write-Host "LUMA frontend: http://localhost:8080"
python -m http.server 8080 --directory $frontendRoot

