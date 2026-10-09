param(
    [int]$Lines = 50,
    [switch]$NoFollow,
    [string]$Filter = "",
    [switch]$ErrorsOnly,
    [switch]$Clear
)

$targetScript = Join-Path $PSScriptRoot "view-backend-logs.ps1"
& $targetScript -Lines $Lines -NoFollow:$NoFollow -Filter $Filter -ErrorsOnly:$ErrorsOnly -Clear:$Clear
