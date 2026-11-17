param([ValidateRange(1,65535)][int]$Port = 18991)
$ErrorActionPreference = "Stop"
$pidFile = Join-Path $env:LOCALAPPDATA "LocalWorkbench\run\local-agent.pid"
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Host "未找到 Local Agent PID 文件"; exit 0 }
$agentPid = [int](Get-Content -Raw -LiteralPath $pidFile)
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$agentPid" -ErrorAction Stop
if (-not $process) { Remove-Item -LiteralPath $pidFile -Force; Write-Host "已清理失效 PID 文件"; exit 0 }
$command = [string]$process.CommandLine
if ($command -notmatch '(?:^|\s)-m\s+src\.local_agent(?:\s|$)' -or $command -notmatch "--port\s+$Port(?:\s|$)") {
  throw "PID $agentPid 不是确认的 Local Agent，已拒绝停止；请先核对进程命令行"
}
$listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object { $_.LocalAddress -eq '127.0.0.1' -and $_.LocalPort -eq $Port })
if ($listeners.Count -ne 1 -or [int]$listeners[0].OwningProcess -ne $agentPid) {
  throw "端口 $Port 的监听归属无法与 PID $agentPid 一致确认，已拒绝停止"
}
Stop-Process -Id $agentPid -Force
Write-Host "已停止 Local Agent PID $agentPid（端口 $Port）"
