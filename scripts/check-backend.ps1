param(
    [string]$BaseUrl = "http://127.0.0.1:5000"
)

$ErrorActionPreference = "Stop"
$healthUrl = "{0}/api/v1/health" -f $BaseUrl.TrimEnd("/")
$health = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 5

[PSCustomObject]@{
    Backend = $health.status
    Database = $health.dependencies.database
    AiService = $health.dependencies.ai_service
    Url = $healthUrl
}

if ($health.status -ne "ok") {
    throw "Backend or database health check failed."
}
if ($health.dependencies.ai_service -ne "ok") {
    throw "Backend is reachable, but the AI service is unavailable."
}
