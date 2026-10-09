param(
    [string]$BaseUrl = "http://127.0.0.1:5000",
    [switch]$RequireAi
)

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
    if ($RequireAi) {
        throw "Backend is reachable, but the AI service is unavailable."
    } else {
        Write-Warning "Backend is online, but AI Engine is currently offline (unavailable)."
    }
}
