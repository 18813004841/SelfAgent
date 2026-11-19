param([Parameter(Mandatory = $true)][int]$Port)

$connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
$processIds = @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($processId in $processIds) {
    if ($processId -and $processId -ne $PID) {
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process) {
            Write-Host "清理端口 $Port 的进程 PID $processId ($($process.ProcessName))"
            Stop-Process -Id $processId -Force -ErrorAction Stop
        }
    }
}
