[CmdletBinding()]
param([string]$ZipFile = "", [string]$BackupDir = "backups", [switch]$Force)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$backupRoot = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $BackupDir))
if ($ZipFile) {
    $archivePath = if (Test-Path -LiteralPath $ZipFile) { (Get-Item -LiteralPath $ZipFile).FullName } else { Join-Path $backupRoot $ZipFile }
} else {
    $latest = Get-ChildItem -LiteralPath $backupRoot -Filter 'luma_backup_*.zip' -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { throw "No backup ZIP was found." }
    $archivePath = $latest.FullName
}
if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf)) { throw "Backup ZIP was not found." }
if (-not $Force) {
    $answer = Read-Host "Stop all Backend processes first. Restore configured database and media? (y/N)"
    if ($answer -notin @('y','Y')) { return }
}
$serviceRoot = Join-Path $repoRoot "backend"
$venvPython = Join-Path $serviceRoot ".venv\Scripts\python.exe"
$pythonPath = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }
$output = & $pythonPath (Join-Path $serviceRoot "recovery.py") restore --archive $archivePath
if ($LASTEXITCODE -ne 0) { throw "Restoration failed." }
$result = $output | ConvertFrom-Json
Write-Host "Restored configured database: $($result.path)"
