# พารามิเตอร์ที่ผู้ใช้ปรับได้เมื่อเรียกสคริปต์
param(
    [string]$Destination
)

# หยุดเมื่อเกิดข้อผิดพลาดและหาตำแหน่งไฟล์จากที่ตั้งสคริปต์

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$serviceRoot = Join-Path $repoRoot "backend"
$pythonPath = Join-Path $serviceRoot ".venv\Scripts\python.exe"
# ตรวจสภาพแวดล้อม Python ของบริการก่อนใช้งาน
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "backend/.venv is missing. Run scripts/run-backend.ps1 first."
}

# ประกอบอาร์กิวเมนต์ให้คำสั่งบำรุงรักษาของ Backend

$maintenanceArgs = @("maintenance.py", "backup")
if ($Destination) {
    $maintenanceArgs += @("--destination", $Destination)
}

# รันจากโฟลเดอร์บริการเพื่อให้พบ .env และคืนตำแหน่งเดิมใน finally

Push-Location $serviceRoot
try {
    & $pythonPath @maintenanceArgs
    if ($LASTEXITCODE -ne 0) { throw "Backend backup failed." }
} finally {
    Pop-Location
}
