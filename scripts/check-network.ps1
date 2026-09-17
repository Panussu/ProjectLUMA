# พารามิเตอร์ที่ผู้ใช้ปรับได้เมื่อเรียกสคริปต์
param(
    [string]$BackendHost = "192.168.1.20",
    [int]$BackendPort = 5000,
    [string]$AiHost = "192.168.1.30",
    [int]$AiPort = 8000
)

# หยุดเมื่อเกิดข้อผิดพลาดและหาตำแหน่งไฟล์จากที่ตั้งสคริปต์

$ErrorActionPreference = "Stop"

# รายการปลายทาง Backend และ AI ที่ต้องตรวจการติดต่อ TCP

$checks = @(
    @{ Name = "Flask backend"; HostName = $BackendHost; Port = $BackendPort },
    @{ Name = "FastAPI AI wrapper"; HostName = $AiHost; Port = $AiPort }
)

# ตรวจพอร์ตของแต่ละบริการและรายงานผล ไม่ได้ยืนยันการสร้างภาพจริง

foreach ($check in $checks) {
    $result = Test-NetConnection -ComputerName $check.HostName -Port $check.Port -WarningAction SilentlyContinue
    # แสดงผลตรวจบริการแต่ละส่วนเป็นข้อมูลที่อ่านง่าย
    [PSCustomObject]@{
        Service = $check.Name
        Address = "{0}:{1}" -f $check.HostName, $check.Port
        Reachable = $result.TcpTestSucceeded
    }
}

