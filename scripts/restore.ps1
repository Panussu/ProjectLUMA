# PowerShell Automated Backup Restoration Script for ProjectLUMA
[CmdletBinding()]
param (
    [string]$ZipFile = "",
    [string]$BackupDir = "backups",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " ProjectLUMA - Database & Media Restore" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Locate backup ZIP file
$targetZipPath = ""
if ($ZipFile -ne "") {
    if (Test-Path $ZipFile) {
        $targetZipPath = (Get-Item $ZipFile).FullName
    } else {
        $candidate = Join-Path (Join-Path $repoRoot $BackupDir) $ZipFile
        if (Test-Path $candidate) {
            $targetZipPath = (Get-Item $candidate).FullName
        }
    }
} else {
    # Pick latest zip file from backups folder
    $backupFolder = Join-Path $repoRoot $BackupDir
    if (Test-Path $backupFolder) {
        $latest = Get-ChildItem -Path $backupFolder -Filter "luma_backup_*.zip" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($latest) {
            $targetZipPath = $latest.FullName
        }
    }
}

if (-not $targetZipPath -or -not (Test-Path $targetZipPath)) {
    Write-Error "No valid backup ZIP archive found. Please specify -ZipFile <path>."
}

Write-Host "[i] Selected backup archive: $targetZipPath" -ForegroundColor Cyan

# Confirm restore unless -Force is specified
if (-not $Force) {
    $confirm = Read-Host "Are you sure you want to restore from this archive? Existing DB and media files will be overwritten. (y/N)"
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Host "[!] Restore operation cancelled by user." -ForegroundColor Yellow
        exit 0
    }
}

# Extract temporary folder
$tempExtractDir = Join-Path $env:TEMP "luma_restore_$(Get-Random)"
if (Test-Path $tempExtractDir) { Remove-Item $tempExtractDir -Recurse -Force }

Write-Host "[i] Extracting archive..." -ForegroundColor Cyan
Expand-Archive -Path $targetZipPath -DestinationPath $tempExtractDir -Force

# Restore luma.db
$extractedDb = Join-Path $tempExtractDir "luma.db"
if (Test-Path $extractedDb) {
    $targetDbPath = Join-Path $repoRoot "backend\luma.db"
    $targetDbDir = Split-Path $targetDbPath -Parent
    if (-not (Test-Path $targetDbDir)) { New-Item -ItemType Directory -Path $targetDbDir -Force | Out-Null }
    
    Copy-Item -Path $extractedDb -Destination $targetDbPath -Force
    Write-Host "[OK] Restored SQLite database to: $targetDbPath" -ForegroundColor Green
} else {
    Write-Host "[!] Warning: luma.db not present in archive." -ForegroundColor Yellow
}

# Restore media directory
$extractedMedia = Join-Path $tempExtractDir "media"
if (Test-Path $extractedMedia) {
    $targetMediaPath = Join-Path $repoRoot "backend\media"
    if (-not (Test-Path $targetMediaPath)) { New-Item -ItemType Directory -Path $targetMediaPath -Force | Out-Null }
    
    Copy-Item -Path "$extractedMedia\*" -Destination $targetMediaPath -Recurse -Force
    Write-Host "[OK] Restored Media directory to: $targetMediaPath" -ForegroundColor Green
} else {
    Write-Host "[!] Warning: media directory not present in archive." -ForegroundColor Yellow
}

# Cleanup temp files
Remove-Item -Path $tempExtractDir -Recurse -Force
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "[OK] Restoration process completed successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
