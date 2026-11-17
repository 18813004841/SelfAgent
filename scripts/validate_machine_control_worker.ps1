$ErrorActionPreference = 'Stop'
$port = 19877
$token = 'validation-token'
$store = Join-Path $env:TEMP ('selfagent-worker-' + [guid]::NewGuid() + '.json')
$env:PYTHONPATH = 'server;shared'
$process = Start-Process python -ArgumentList '-m','control_center.server','--host','127.0.0.1','--port',$port,'--token',$token,'--store',$store -WorkingDirectory (Get-Location) -PassThru -WindowStyle Hidden
try {
  $headers = @{ Authorization = "Bearer $token" }
  $ready = $false
  for ($i = 0; $i -lt 30; $i++) { Start-Sleep -Milliseconds 200; try { if ((Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/health").StatusCode -eq 200) { $ready = $true; break } } catch {} }
  if (-not $ready) { throw 'health timeout' }
  $body = @{ machine_id='validation-worker'; hostname='validation'; os='windows'; capabilities=@('shell'); meta=@{ local_ips=@('127.0.0.1') } } | ConvertTo-Json -Depth 5
  $registered = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$port/api/workers/register" -Headers $headers -ContentType 'application/json' -Body $body
  if ($registered.ok -ne $true) { throw 'register failed' }
  $workers = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/workers" -Headers $headers
  if (-not ($workers.workers.machine_id -contains 'validation-worker')) { throw 'worker missing' }
  Write-Output 'worker registration and listing passed'
} finally { if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force } }
