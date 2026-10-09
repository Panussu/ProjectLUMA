param(
    [int]$Lines = 50,
    [switch]$NoFollow,
    [string]$Filter = "",
    [switch]$ErrorsOnly,
    [switch]$Clear
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$logFile = Join-Path $repoRoot "backend\logs\backend.log"
$logDir = Split-Path -Parent $logFile

if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

if ($Clear) {
    if (Test-Path -LiteralPath $logFile) {
        Clear-Content -LiteralPath $logFile
        Write-Host "Log cleared: $logFile" -ForegroundColor Green
    } else {
        Write-Host "Log file not found." -ForegroundColor Yellow
    }
    exit 0
}

if (-not (Test-Path -LiteralPath $logFile)) {
    New-Item -ItemType File -Path $logFile -Force | Out-Null
}

$backendStatus = "Offline"
$backendColor = "DarkGray"
try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/v1/health" -Method Get -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    if ($resp.status -eq "ok") {
        $backendStatus = "Online (Healthy)"
        $backendColor = "Green"
    } else {
        $backendStatus = "Online (Degraded)"
        $backendColor = "Yellow"
    }
} catch {
    $backendStatus = "Offline / Not Responding"
    $backendColor = "DarkGray"
}

$fileInfo = Get-Item -LiteralPath $logFile
$fileSizeKb = [math]::Round($fileInfo.Length / 1KB, 2)

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "               ProjectLUMA - Backend Logs                 " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Log File:    $logFile" -ForegroundColor Gray
Write-Host "File Size:   $fileSizeKb KB" -ForegroundColor Gray
Write-Host "Backend:     " -NoNewline -ForegroundColor Gray
Write-Host $backendStatus -ForegroundColor $backendColor

if ($Filter) {
    Write-Host "Filter:      '$Filter'" -ForegroundColor Magenta
}
if ($ErrorsOnly) {
    Write-Host "Mode:        Errors Only" -ForegroundColor Red
}
if (-not $NoFollow) {
    Write-Host "Stream:      Real-time (Press Ctrl+C to exit)" -ForegroundColor DarkCyan
}
Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray

function Print-Line {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) { return }

    if ($Filter -and ($Text.IndexOf($Filter, [System.StringComparison]::OrdinalIgnoreCase) -lt 0)) {
        return
    }

    $isError = $Text -match "ERROR|CRITICAL|Traceback|Exception"
    if ($ErrorsOnly -and (-not $isError)) {
        return
    }

    if ($isError) {
        Write-Host $Text -ForegroundColor Red
    } elseif ($Text -match "WARNING|WARN") {
        Write-Host $Text -ForegroundColor Yellow
    } elseif ($Text -match '"\s(200|201|204)\b') {
        Write-Host $Text -ForegroundColor Green
    } elseif ($Text -match '"\s(400|401|403|404|422|500)\b') {
        Write-Host $Text -ForegroundColor Magenta
    } elseif ($Text -match "\[INFO\]") {
        Write-Host $Text -ForegroundColor Gray
    } else {
        Write-Host $Text -ForegroundColor White
    }
}

if ($NoFollow) {
    $content = Get-Content -LiteralPath $logFile -Tail $Lines -ErrorAction SilentlyContinue
    if ($content) {
        foreach ($line in $content) {
            Print-Line -Text $line
        }
    } else {
        Write-Host "(No log records found)" -ForegroundColor DarkGray
    }
} else {
    try {
        Get-Content -LiteralPath $logFile -Tail $Lines -Wait | ForEach-Object {
            Print-Line -Text $_
        }
    } catch {
        # Exit smoothly on Ctrl+C
    }
}
