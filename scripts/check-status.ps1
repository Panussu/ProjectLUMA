# PowerShell Status Checker for ProjectLUMA Services
[CmdletBinding()]
param (
    [string]$BackendUrl = "http://localhost:5000/api/v1/health",
    [string]$AiUrl = "http://localhost:8000/health",
    [string]$FrontendUrl = "http://localhost:80"
)

$ErrorActionPreference = "SilentlyContinue"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " ProjectLUMA - Health & Status Check" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

function Test-Endpoint {
    param (
        [string]$Name,
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4
        if ($response.StatusCode -eq 200) {
            Write-Host ("[ONLINE] {0,-20} -> {1} (HTTP 200)" -f $Name, $Url) -ForegroundColor Green
        } else {
            Write-Host ("[WARN]   {0,-20} -> {1} (HTTP {2})" -f $Name, $Url, $response.StatusCode) -ForegroundColor Yellow
        }
    } catch {
        Write-Host ("[OFFLINE]{0,-20} -> {1}" -f $Name, $Url) -ForegroundColor Red
    }
}

Test-Endpoint -Name "Frontend (Nginx/Dev)" -Url $FrontendUrl
Test-Endpoint -Name "Backend (Flask)" -Url $BackendUrl
Test-Endpoint -Name "AI Engine (FastAPI)" -Url $AiUrl

Write-Host "========================================" -ForegroundColor Cyan
