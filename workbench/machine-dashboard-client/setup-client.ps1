param(
  [Parameter(Mandatory=$true)][string]$DashboardUrl,
  [switch]$Start
)
$ErrorActionPreference = "Stop"
$dashboardOrigin = $null
if (-not [Uri]::TryCreate($DashboardUrl, [UriKind]::Absolute, [ref]$dashboardOrigin) -or
    $dashboardOrigin.Scheme -notin @('http', 'https') -or
    $dashboardOrigin.UserInfo -or $dashboardOrigin.Query -or $dashboardOrigin.Fragment -or
    $dashboardOrigin.AbsolutePath -ne '/') {
  throw "DashboardUrl 必须是工作台网址的来源，例如 http://192.168.1.10:18888（不含路径、凭据或查询参数）"
}
$clientRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $clientRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  & python -m venv (Join-Path $clientRoot ".venv")
  if ($LASTEXITCODE -ne 0) { throw "无法创建客户机虚拟环境" }
}
if (-not (Test-Path $python)) { throw "客户机 Python 不可用: $python" }
$env:WORKBENCH_DASHBOARD_URL = $dashboardOrigin.GetLeftPart([UriPartial]::Authority)
$env:WORKBENCH_CLIENT_PYTHON = $python
$configRoot = Join-Path $env:LOCALAPPDATA "LocalWorkbench\config"
$storage = Join-Path $env:LOCALAPPDATA "LocalWorkbench\client\storage"
New-Item -ItemType Directory -Force $configRoot, $storage | Out-Null
$config = Join-Path $configRoot "settings.json"
if (-not (Test-Path $config)) {
  $json = @{ storage_dir = $storage; dashboard_url = $env:WORKBENCH_DASHBOARD_URL; local_codex_url = "ws://127.0.0.1:4500"; central_token = ""; machine_id = $env:COMPUTERNAME } | ConvertTo-Json
  [IO.File]::WriteAllText($config, $json, [Text.UTF8Encoding]::new($false))
} else {
  try {
    $existing = Get-Content -Raw -LiteralPath $config | ConvertFrom-Json
    if ($existing -isnot [PSCustomObject]) { throw "配置必须是 JSON 对象" }
    $existing | Add-Member -Force -NotePropertyName dashboard_url -NotePropertyValue $env:WORKBENCH_DASHBOARD_URL
    if (-not $existing.storage_dir) { $existing | Add-Member -Force -NotePropertyName storage_dir -NotePropertyValue $storage }
    $temporaryConfig = "$config.tmp"
    [IO.File]::WriteAllText($temporaryConfig, ($existing | ConvertTo-Json -Depth 32), [Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporaryConfig -Destination $config -Force
  } catch { throw "客户机配置无效，请备份后修复: $config" }
}
Write-Host "客户机配置: $config"
Write-Host "本地保存目录: $storage"
Write-Host "工作台地址: $env:WORKBENCH_DASHBOARD_URL"
if ($Start) {
  Push-Location $clientRoot
  try {
    & $python -m src.local_agent --host 127.0.0.1 --port 18991 --dashboard-url $env:WORKBENCH_DASHBOARD_URL
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  } finally { Pop-Location }
}
