# PowerShell Backup Script for ProjectLUMA (SQLite DB & Media files)
[CmdletBinding()]
param (
    [string]$BackupDir = "backups",
    [int]$RetentionDays = 7
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$targetBackupFolder = Join-Path $repoRoot (Join-Path $BackupDir "luma_backup_$timestamp")
$zipPath = "$targetBackupFolder.zip"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " ProjectLUMA - Backup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Create backup folder
if (-not (Test-Path -Path $targetBackupFolder)) {
    New-Item -ItemType Directory -Path $targetBackupFolder -Force | Out-Null
}

# 2. Find and copy SQLite database file
$dbFound = $false
$dbPaths = @(
    (Join-Path $repoRoot "backend\luma.db"),
    (Join-Path $repoRoot "backend\instance\luma.db"),
    (Join-Path $repoRoot "data\luma.db")
)

foreach ($path in $dbPaths) {
    if (Test-Path -Path $path) {
        $dest = Join-Path $targetBackupFolder "luma.db"
        Copy-Item -Path $path -Destination $dest -Force
        Write-Host "[OK] Backuped Database from: $path" -ForegroundColor Green
        $dbFound = $true
        break
    }
}

if (-not $dbFound) {
    Write-Host "[!] Warning: Local SQLite database file not found in standard paths. Skipping DB copy." -ForegroundColor Yellow
}

# 3. Copy Media directory
$mediaPaths = @(
    (Join-Path $repoRoot "backend\media"),
    (Join-Path $repoRoot "media")
)

$mediaFound = $false
foreach ($mPath in $mediaPaths) {
    if (Test-Path -Path $mPath) {
        $destMedia = Join-Path $targetBackupFolder "media"
        Copy-Item -Path $mPath -Destination $destMedia -Recurse -Force
        Write-Host "[OK] Backuped Media files from: $mPath" -ForegroundColor Green
        $mediaFound = $true
        break
    }
}

if (-not $mediaFound) {
    Write-Host "[!] Warning: Media folder not found. Skipping media backup." -ForegroundColor Yellow
}

# 4. Compress to ZIP Archive
Write-Host "[i] Compressing backup to: $zipPath..." -ForegroundColor Cyan
Compress-Archive -Path "$targetBackupFolder\*" -DestinationPath $zipPath -Force
Remove-Item -Path $targetBackupFolder -Recurse -Force

Write-Host "[OK] Backup completed successfully: $zipPath" -ForegroundColor Green

# 5. Prune backups older than $RetentionDays
$backupParent = Join-Path $repoRoot $BackupDir
if (Test-Path -Path $backupParent) {
    $cutoffDate = (Get-Date).AddDays(-$RetentionDays)
    Get-ChildItem -Path $backupParent -Filter "luma_backup_*.zip" | Where-Object { $_.LastWriteTime -lt $cutoffDate } | ForEach-Object {
        Remove-Item -Path $_.FullName -Force
        Write-Host "[i] Pruned old backup file: $($_.Name)" -ForegroundColor Gray
    }
}

Write-Host "========================================" -ForegroundColor Cyan
