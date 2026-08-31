param(
    [string]$BackendHost = "192.168.1.20",
    [int]$BackendPort = 5000,
    [string]$AiHost = "192.168.1.30",
    [int]$AiPort = 8000
)

$ErrorActionPreference = "Stop"

$checks = @(
    @{ Name = "Flask backend"; HostName = $BackendHost; Port = $BackendPort },
    @{ Name = "FastAPI AI wrapper"; HostName = $AiHost; Port = $AiPort }
)

foreach ($check in $checks) {
    $result = Test-NetConnection -ComputerName $check.HostName -Port $check.Port -WarningAction SilentlyContinue
    [PSCustomObject]@{
        Service = $check.Name
        Address = "{0}:{1}" -f $check.HostName, $check.Port
        Reachable = $result.TcpTestSucceeded
    }
}

