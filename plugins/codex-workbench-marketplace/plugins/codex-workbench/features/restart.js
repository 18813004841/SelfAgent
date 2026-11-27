const cp = require('node:child_process');

// The helper outlives the MCP process. Match the packaged Codex executable,
// never every ChatGPT.exe or unrelated Codex CLI process.
const script = String.raw`
$ErrorActionPreference = 'Stop'
$logDir = Join-Path $env:LOCALAPPDATA 'SelfAgent\codex-plugin'
try {
  New-Item -ItemType Directory -Force -Path $logDir | Out-Null
  $log = Join-Path $logDir 'restart.log'
  $targets = @(Get-CimInstance Win32_Process -Filter "Name = 'ChatGPT.exe'" | Where-Object {
    $_.ExecutablePath -match '[\\/]WindowsApps[\\/]OpenAI\.Codex_[^\\/]+[\\/]app[\\/]ChatGPT\.exe$' -and
    $_.CommandLine -notmatch '(?:^|\s)--type='
  })
  if ($targets.Count -ne 1) { throw "Expected one Codex desktop main process; found $($targets.Count)." }
  $target = $targets[0]
  $app = @(Get-StartApps | Where-Object { $_.AppID -match '^OpenAI\.Codex_[^!]+!App$' })
  if ($app.Count -ne 1) { throw "Expected one Codex app entry; found $($app.Count)." }
  [Console]::Out.WriteLine('READY')
  [Console]::Out.Flush()
  Start-Sleep -Seconds 3
  $current = Get-CimInstance Win32_Process -Filter "ProcessId = $($target.ProcessId)"
  if ($null -eq $current -or $current.CreationDate -ne $target.CreationDate -or $current.ExecutablePath -ne $target.ExecutablePath) { throw 'Codex process changed before restart.' }
  $process = Get-Process -Id $target.ProcessId -ErrorAction Stop
  if ($process.MainWindowHandle -ne 0) { $null = $process.CloseMainWindow() }
  if (-not $process.WaitForExit(5000)) { Stop-Process -Id $target.ProcessId -Force -ErrorAction Stop; $process.WaitForExit(10000) | Out-Null }
  if (-not $process.HasExited) { throw 'Codex did not exit.' }
  Start-Process explorer.exe -ArgumentList ('shell:AppsFolder\' + $app[0].AppID)
  Add-Content -LiteralPath $log -Value "$(Get-Date -Format o) Requested Codex restart."
} catch {
  [Console]::Out.WriteLine('ERROR: ' + $_.Exception.Message)
  [Console]::Out.Flush()
  if (-not $log) { $log = Join-Path $env:TEMP 'selfagent-codex-restart.log' }
  try { Add-Content -LiteralPath $log -Value "$(Get-Date -Format o) Restart failed: $($_.Exception.Message)" } catch {}
}
`;
function restart(options = {}) {
 const platform = options.platform || process.platform;
 if (platform !== 'win32') throw Error('当前仅支持在 Windows 重启 Codex');
 const spawn = options.spawn || cp.spawn;
 const encoded = Buffer.from(script, 'utf16le').toString('base64');
 return new Promise((resolve, reject) => {
  let child, settled = false, output = '';
  const finish = (err) => { if (settled) return; settled = true; clearTimeout(timer); if (err) { child?.kill(); reject(err); } else { child.stdout.unref?.(); child.unref(); resolve({message:'重启助手已就绪，Codex 即将关闭。'}); } };
  const timer = setTimeout(() => finish(Error('重启助手未响应，请手动重启 Codex')), 10000);
  try { child = spawn('powershell.exe', ['-NoProfile','-NonInteractive','-WindowStyle','Hidden','-EncodedCommand',encoded], {detached:true, windowsHide:true, stdio:['ignore','pipe','ignore']}); }
  catch (e) { return finish(Error(`无法启动重启助手：${e.message}`)); }
  child.once('error', e => finish(Error(`无法启动重启助手：${e.message}`)));
  child.once('exit', () => finish(Error('重启助手提前退出，请手动重启 Codex')));
  child.stdout.setEncoding('utf8');
  child.stdout.on('data', chunk => { output += chunk; const lines=output.split(/\r?\n/); output=lines.pop(); for (const line of lines) { if (line === 'READY') return finish(); if (line.startsWith('ERROR:')) return finish(Error(line.slice(6).trim())); } });
 });
}
module.exports = {restart, script};
