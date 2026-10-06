# PowerShell Deployment Orchestrator for ProjectLUMA
[CmdletBinding()]
param (
    [ValidateSet("dev", "prod")]
    [string]$Env = "dev",

    [switch]$Build,
    [switch]$Down
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " ProjectLUMA - Deployment Script ($Env)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

$composeFile = if ($Env -eq "prod") { "docker-compose.prod.yml" } else { "docker-compose.yml" }
$fullPath = Join-Path $repoRoot $composeFile

if (-not (Test-Path $fullPath)) {
    Write-Error "Compose file not found: $fullPath"
}

if ($Down) {
    Write-Host "[i] Stopping Docker Compose stack..." -ForegroundColor Yellow
    docker compose -f $fullPath down
    Write-Host "[OK] Stack stopped." -ForegroundColor Green
    exit 0
}

$cmdArgs = @("compose", "-f", $fullPath, "up", "-d")
if ($Build) {
    $cmdArgs += "--build"
}

Write-Host "[i] Starting Docker Compose ($composeFile)..." -ForegroundColor Cyan
Push-Location $repoRoot
try {
    docker @cmdArgs
    Write-Host "[OK] ProjectLUMA stack launched successfully." -ForegroundColor Green
} finally {
    Pop-Location
}

Write-Host "========================================" -ForegroundColor Cyan
