# PowerShell QA Automated Execution Script for ProjectLUMA
[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " ProjectLUMA - Automated QA Test Suite Runner" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$passed = $true

# Step 1: Run Pytest
Write-Host "`n[STEP 1/3] Running Python Pytest Suite..." -ForegroundColor Yellow
Push-Location $repoRoot
try {
    python -m pytest --tb=short
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[PASS] Pytest test suite executed successfully!" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Pytest test suite failed (Exit code: $LASTEXITCODE)." -ForegroundColor Red
        $passed = $false
    }
} finally {
    Pop-Location
}

# Step 2: Check JS Syntax
Write-Host "`n[STEP 2/3] Checking Frontend JavaScript Syntax..." -ForegroundColor Yellow
$appJsPath = Join-Path $repoRoot "frontend\assets\app.js"
if (Test-Path $appJsPath) {
    node --check $appJsPath
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[PASS] Frontend app.js syntax check passed!" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] JavaScript syntax error detected." -ForegroundColor Red
        $passed = $false
    }
} else {
    Write-Host "[SKIP] frontend/assets/app.js not found in current branch workspace." -ForegroundColor Gray
}

# Step 3: Check Docker Compose Config
Write-Host "`n[STEP 3/3] Validating Docker Compose Configuration..." -ForegroundColor Yellow
Push-Location $repoRoot
try {
    docker compose config --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[PASS] Docker compose configuration is valid!" -ForegroundColor Green
    } else {
        Write-Host "[FAIL] Docker compose configuration error." -ForegroundColor Red
        $passed = $false
    }
} finally {
    Pop-Location
}

Write-Host "`n==========================================================" -ForegroundColor Cyan
if ($passed) {
    Write-Host " [QA RESULT] ALL CHECKS PASSED - READY FOR PRODUCTION / DEMO 🏆" -ForegroundColor Green
} else {
    Write-Host " [QA RESULT] CHECKS FAILED - PLEASE REVIEW LOGS ABOVE ❌" -ForegroundColor Red
}
Write-Host "==========================================================" -ForegroundColor Cyan
