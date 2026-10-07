# PowerShell Network & Port Connectivity Diagnostics for ProjectLUMA 3-PC Deployment
[CmdletBinding()]
param (
    [string]$BackendHost = "192.168.1.20",
    [int]$BackendPort = 5000,
    [string]$AiHost = "192.168.1.30",
    [int]$AiPort = 8000,
    [string]$FrontendHost = "192.168.1.10",
    [int]$FrontendPort = 80
)

$ErrorActionPreference = "SilentlyContinue"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " ProjectLUMA - 3-PC VLAN Network Connectivity Diagnostics" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

function Test-PortConnection {
    param (
        [string]$RoleName,
        [string]$TargetHost,
        [int]$TargetPort
    )

    Write-Host ("[i] Testing connection to {0} ({1}:{2})..." -f $RoleName, $TargetHost, $TargetPort) -NoNewline

    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $asyncResult = $tcpClient.BeginConnect($TargetHost, $TargetPort, $null, $null)
    $waitHandle = $asyncResult.AsyncWaitHandle.WaitOne(3000, $false)

    if (-not $waitHandle) {
        $tcpClient.Close()
        Write-Host " -> [FAILED] (Connection Timeout)" -ForegroundColor Red
        return $false
    } else {
        try {
            $tcpClient.EndConnect($asyncResult)
            $tcpClient.Close()
            Write-Host " -> [SUCCESS] (Port Open)" -ForegroundColor Green
            return $true
        } catch {
            Write-Host " -> [FAILED] (Connection Refused)" -ForegroundColor Red
            return $false
        }
    }
}

$frontendOk = Test-PortConnection -RoleName "PC 2 (Frontend Nginx)" -TargetHost $FrontendHost -TargetPort $FrontendPort
$backendOk  = Test-PortConnection -RoleName "PC 3 (Backend Flask API)" -TargetHost $BackendHost -TargetPort $BackendPort
$aiOk       = Test-PortConnection -RoleName "PC 1 (AI Engine FastAPI)" -TargetHost $AiHost -TargetPort $AiPort

Write-Host "----------------------------------------------------------" -ForegroundColor Gray
if ($frontendOk -and $backendOk -and $aiOk) {
    Write-Host "[OK] All 3-PC VLAN network ports are reachable!" -ForegroundColor Green
} else {
    Write-Host "[!] Network warning: Some nodes are unreachable. Check IP, firewall rules, or service status." -ForegroundColor Yellow
}
Write-Host "==========================================================" -ForegroundColor Cyan
