# พารามิเตอร์ที่ผู้ใช้ปรับได้เมื่อเรียกสคริปต์
param(
    [string]$BaseUrl = "http://127.0.0.1:5000"
)

# หยุดเมื่อเกิดข้อผิดพลาดและหาตำแหน่งไฟล์จากที่ตั้งสคริปต์

$ErrorActionPreference = "Stop"
# อ่านสถานะรวมและสถานะบริการที่ Backend พึ่งพา
$healthUrl = "{0}/api/v1/health" -f $BaseUrl.TrimEnd("/")
$health = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 5

# แสดงผลตรวจบริการแต่ละส่วนเป็นข้อมูลที่อ่านง่าย

[PSCustomObject]@{
    Backend = $health.status
    Database = $health.dependencies.database
    AiService = $health.dependencies.ai_service
    Url = $healthUrl
}

# แจ้งข้อผิดพลาดเมื่อ Backend หรือฐานข้อมูลไม่พร้อม

if ($health.status -ne "ok") {
    throw "Backend or database health check failed."
}
# แจ้งแยกกรณี Backend ติดต่อได้แต่ AI ไม่พร้อม
if ($health.dependencies.ai_service -ne "ok") {
    throw "Backend is reachable, but the AI service is unavailable."
}
