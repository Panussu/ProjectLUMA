# Run all automated checks and return a failing exit code when any check fails.
[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$passed = $true

# Prefer the project environment so installed dependencies match the application.
$pythonPath = Join-Path $repoRoot "backend/.venv/Scripts/python.exe"
if (-not (Test-Path $pythonPath)) { $pythonPath = "python" }

function Invoke-Check {
    param([string]$Name, [string]$Executable, [string[]]$Arguments)
    Write-Host "Checking $Name..."
    try {
        & $Executable @Arguments
        if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
        Write-Host "[PASS] $Name"
    } catch {
        # Missing programs must fail the checks instead of reusing a stale exit code.
        Write-Host "[FAIL] $Name : $_" -ForegroundColor Red
        $script:passed = $false
    }
}

Push-Location $repoRoot
try {
    Invoke-Check -Name "Python tests" -Executable $pythonPath -Arguments @("-m", "pytest", "--tb=short")
    Invoke-Check -Name "JavaScript syntax" -Executable "node" -Arguments @("--check", "frontend/assets/app.js")
    Invoke-Check -Name "Frontend tests" -Executable "node" -Arguments @("--test", "tests/test_frontend.cjs")
    Invoke-Check -Name "Compose configuration" -Executable "docker" -Arguments @("compose", "config", "--quiet")
} finally {
    Pop-Location
}

# Automated checks do not establish real GPU or deployment readiness.
if (-not $passed) {
    Write-Host "Checks failed. Review the errors above." -ForegroundColor Red
    exit 1
}
Write-Host "Automated checks passed. Live deployment still requires verification." -ForegroundColor Green
exit 0
