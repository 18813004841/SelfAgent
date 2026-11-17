$ErrorActionPreference = 'Stop'
$project = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../Tools/machine-control'))
$python = Join-Path $project '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'machine-control .venv is required' }
$ip = [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) | Where-Object { $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and -not [System.Net.IPAddress]::IsLoopback($_) -and $_.ToString() -notlike '169.254.*' } | Select-Object -First 1 -ExpandProperty IPAddressToString
if (-not $ip) { throw 'no non-loopback IPv4 address available' }
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0); $listener.Start(); $port = $listener.LocalEndpoint.Port; $listener.Stop()
$token = 'lan-validation-token'; $store = Join-Path $env:TEMP ('selfagent-lan-' + [guid]::NewGuid() + '.json')
$center = Start-Process $python -ArgumentList '-m','control_center.server','--host','0.0.0.0','--port',$port,'--token',$token,'--store',$store -WorkingDirectory $project -PassThru -WindowStyle Hidden
$worker = $null
try {
  $ready = $false
  for ($i=0; $i -lt 40; $i++) { Start-Sleep -Milliseconds 200; try { if ((Invoke-WebRequest -UseBasicParsing "http://${ip}:$port/health").StatusCode -eq 200) { $ready=$true; break } } catch {} }
  if (-not $ready) { throw "LAN-visible center health timeout at ${ip}:$port" }
  $worker = Start-Process $python -ArgumentList '-m','control_worker.client','--server',"http://${ip}:$port",'--token',$token,'--machine-id','lan-validation-worker','--poll-interval','1' -WorkingDirectory $project -PassThru -WindowStyle Hidden
  $headers = @{ Authorization = "Bearer $token" }; $registered = $false
  for ($i=0; $i -lt 40; $i++) { Start-Sleep -Milliseconds 250; try { $workers=(Invoke-RestMethod -Uri "http://${ip}:$port/api/workers" -Headers $headers).workers; if ($workers.machine_id -contains 'lan-validation-worker') {$registered=$true;break} } catch {} }
  if (-not $registered) { throw 'LAN worker registration timeout' }
  Write-Output "LAN-visible binding and worker registration passed: ${ip}:$port"
} finally {
  if ($worker -and -not $worker.HasExited) { Stop-Process -Id $worker.Id -Force }
  if ($center -and -not $center.HasExited) { Stop-Process -Id $center.Id -Force }
  Start-Sleep -Milliseconds 300
  if ($worker -and -not $worker.HasExited) { throw 'worker process still running' }
  if ($center -and -not $center.HasExited) { throw 'center process still running' }
}
