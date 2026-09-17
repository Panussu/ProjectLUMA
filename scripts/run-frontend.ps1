# หยุดเมื่อเกิดข้อผิดพลาดและหาตำแหน่งไฟล์จากที่ตั้งสคริปต์
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$frontendRoot = Join-Path $repoRoot "frontend"

# เปิดเว็บพัฒนาแบบไฟล์สถิตบนพอร์ต 8080 โดย API ยังอยู่บน Backend

Write-Host "LUMA frontend: http://localhost:8080"
python -m http.server 8080 --directory $frontendRoot

