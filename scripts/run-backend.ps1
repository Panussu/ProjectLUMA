# พารามิเตอร์ที่ผู้ใช้ปรับได้เมื่อเรียกสคริปต์
param(
    [switch]$Vlan
)

# หยุดเมื่อเกิดข้อผิดพลาดและหาตำแหน่งไฟล์จากที่ตั้งสคริปต์

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$serviceRoot = Join-Path $repoRoot "backend"
$pythonPath = Join-Path $serviceRoot ".venv\Scripts\python.exe"
$pipPath = Join-Path $serviceRoot ".venv\Scripts\pip.exe"
$environmentPath = Join-Path $serviceRoot ".env"

# ตรวจสภาพแวดล้อม Python ของบริการก่อนใช้งาน

if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv (Join-Path $serviceRoot ".venv")
}

# ติดตั้งไลบรารีตามรายการที่กำหนดไว้ในบริการ

& $pipPath install -r (Join-Path $serviceRoot "requirements.txt") --disable-pip-version-check

# เลือกตัวอย่างค่าพัฒนาหรือ VLAN และให้แก้ค่าตัวอย่างก่อนเปิดบนเครือข่าย

if (-not (Test-Path -LiteralPath $environmentPath)) {
    $templateName = if ($Vlan) { ".env.vlan.example" } else { ".env.example" }
    Copy-Item -LiteralPath (Join-Path $serviceRoot $templateName) -Destination $environmentPath
    Write-Host "Created backend/.env from $templateName. Edit its secrets and addresses before starting."
    if ($Vlan) {
        throw "VLAN configuration contains placeholders. Edit backend/.env, then run this command again."
    }
}

# รันจากโฟลเดอร์บริการเพื่อให้พบ .env และคืนตำแหน่งเดิมใน finally

Push-Location $serviceRoot
try {
    & $pythonPath run.py
} finally {
    Pop-Location
}
