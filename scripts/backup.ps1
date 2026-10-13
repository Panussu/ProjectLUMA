[CmdletBinding()]
param([string]$BackupDir = "backups", [ValidateRange(1,36500)][int]$RetentionDays = 7)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$serviceRoot = Join-Path $repoRoot "backend"
$venvPython = Join-Path $serviceRoot ".venv\Scripts\python.exe"
$pythonPath = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }
$destination = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $BackupDir))
$output = & $pythonPath (Join-Path $serviceRoot "recovery.py") backup --destination $destination
if ($LASTEXITCODE -ne 0) { throw "Configured backup failed." }
$result = $output | ConvertFrom-Json
Write-Host "Backup created: $($result.path)"
$cutoff = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem -LiteralPath $destination -Filter 'luma_backup_*.zip' -File | Where-Object LastWriteTime -LT $cutoff | ForEach-Object { Remove-Item -LiteralPath $_.FullName }
