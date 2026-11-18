param(
  [Parameter(Mandatory=$true)][string]$PackagePath,
  [string]$DashboardUrl = "",
  [switch]$Start
)
$ErrorActionPreference = "Stop"
$clientRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$package = (Resolve-Path -LiteralPath $PackagePath).Path
$stage = Join-Path ([IO.Path]::GetTempPath()) ("workbench-client-update-" + [Guid]::NewGuid().ToString("N"))
$backup = "$clientRoot.previous"
New-Item -ItemType Directory -Path $stage | Out-Null
try {
  Expand-Archive -LiteralPath $package -DestinationPath $stage -Force
  $source = Join-Path $stage "machine-dashboard-client"
  if (-not (Test-Path (Join-Path $source "VERSION")) -or -not (Test-Path (Join-Path $source "src\local_agent.py"))) {
    throw "升级包缺少 VERSION 或 Local Agent 入口"
  }
  $version = (Get-Content -Raw -LiteralPath (Join-Path $source "VERSION")).Trim()
  if ($version -notmatch '^\d+\.\d+\.\d+$') { throw "升级包版本号无效: $version" }
  $pidFile = Join-Path $env:LOCALAPPDATA "LocalWorkbench\run\local-agent.pid"
  if (Test-Path $pidFile) {
    $agentProcessId = [int](Get-Content -Raw -LiteralPath $pidFile).Trim()
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$agentProcessId"
    if ($process) {
      if ($process.CommandLine -notmatch 'src\.local_agent') { throw "PID 不属于 Local Agent，拒绝停止" }
      Stop-Process -Id $agentProcessId -Force
      Wait-Process -Id $agentProcessId -ErrorAction SilentlyContinue
    }
  }
  if (Test-Path $backup) { throw "旧备份仍存在，请先确认并保留备份后重试: $backup" }
  if (Test-Path $clientRoot) { Move-Item -LiteralPath $clientRoot -Destination $backup }
  try {
    Move-Item -LiteralPath $source -Destination $clientRoot
  } catch {
    if (Test-Path $backup) { Move-Item -LiteralPath $backup -Destination $clientRoot }
    throw
  }
  $python = Join-Path $clientRoot ".venv\Scripts\python.exe"
  if (-not (Test-Path $python)) { & python -m venv (Join-Path $clientRoot ".venv") }
  if (-not (Test-Path $python)) { throw "无法创建升级后的 Python 环境" }
  Write-Host "本机客户端已更新到 $version"
  if ($Start) {
    if (-not $DashboardUrl) { $DashboardUrl = "http://127.0.0.1:18888" }
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $clientRoot "setup-client.ps1") -DashboardUrl $DashboardUrl -Start
  }
} catch {
  if (-not (Test-Path $clientRoot) -and (Test-Path $backup)) { Move-Item -LiteralPath $backup -Destination $clientRoot }
  throw
} finally {
  if (Test-Path $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}
