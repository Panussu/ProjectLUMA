# หยุดเมื่อเกิดข้อผิดพลาดและหาตำแหน่งไฟล์จากที่ตั้งสคริปต์
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$serviceRoot = Join-Path $repoRoot "ai-engine"
$pythonPath = Join-Path $serviceRoot ".venv\Scripts\python.exe"
$pipPath = Join-Path $serviceRoot ".venv\Scripts\pip.exe"

# ตรวจสภาพแวดล้อม Python ของบริการก่อนใช้งาน

if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv (Join-Path $serviceRoot ".venv")
}

# ติดตั้งไลบรารีตามรายการที่กำหนดไว้ในบริการ

& $pipPath install -r (Join-Path $serviceRoot "requirements.txt") --disable-pip-version-check

# สร้าง .env เฉพาะเมื่อยังไม่มี เพื่อไม่เขียนทับค่าของผู้ใช้

if (-not (Test-Path -LiteralPath (Join-Path $serviceRoot ".env"))) {
    Copy-Item -LiteralPath (Join-Path $serviceRoot ".env.example") -Destination (Join-Path $serviceRoot ".env")
    Write-Host "Created ai-engine/.env from the example. Change its token before LAN deployment."
}

# รันจากโฟลเดอร์บริการเพื่อให้พบ .env และคืนตำแหน่งเดิมใน finally

Push-Location $serviceRoot
try {
    & $pythonPath app.py
} finally {
    Pop-Location
}

