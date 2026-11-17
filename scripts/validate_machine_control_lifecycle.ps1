$ErrorActionPreference = 'Stop'
$port = 19876
$store = Join-Path $env:TEMP ('selfagent-center-' + [guid]::NewGuid() + '.json')
$env:PYTHONPATH = 'server;shared'
$process = Start-Process python -ArgumentList '-m','control_center.server','--host','127.0.0.1','--port',$port,'--store',$store -WorkingDirectory (Get-Location) -PassThru -WindowStyle Hidden
try {
  $ready = $false
  for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 200
    try { if ((Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/health" -TimeoutSec 1).StatusCode -eq 200) { $ready = $true; break } } catch {}
  }
  if (-not $ready) { throw 'health timeout' }
  Write-Output 'machine-control lifecycle health passed'
} finally {
  if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
  Start-Sleep -Milliseconds 300
  try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/health" -TimeoutSec 1 | Out-Null; throw 'port still serving' } catch { if ($_.Exception.Message -eq 'port still serving') { throw } }
  Write-Output 'machine-control lifecycle shutdown passed'
}
