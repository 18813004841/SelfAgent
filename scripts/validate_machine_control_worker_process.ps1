$ErrorActionPreference = 'Stop'
$project = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../Tools/machine-control'))
$python = Join-Path $project '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'machine-control .venv is required; run bootstrap_projects.py first' }
$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = $listener.LocalEndpoint.Port
$listener.Stop()
$token = 'worker-process-token'
$store = Join-Path $env:TEMP ('selfagent-worker-process-' + [guid]::NewGuid() + '.json')
$previousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = $null
$center = Start-Process $python -ArgumentList '-m','control_center.server','--host','127.0.0.1','--port',$port,'--token',$token,'--store',$store -WorkingDirectory $project -PassThru -WindowStyle Hidden
$worker = $null
try {
  $ready = $false
  for ($i = 0; $i -lt 30; $i++) { Start-Sleep -Milliseconds 200; try { if ((Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/health").StatusCode -eq 200) { $ready = $true; break } } catch {} }
  if (-not $ready) { throw 'center health timeout' }
  if ($center.HasExited) { throw 'owned center exited before readiness' }
  $worker = Start-Process $python -ArgumentList '-m','control_worker.client','--server',"http://127.0.0.1:$port",'--token',$token,'--machine-id','validation-worker-process','--poll-interval','1','--allow-command','ping' -WorkingDirectory $project -PassThru -WindowStyle Hidden
  $registered = $false
  for ($i = 0; $i -lt 30; $i++) { Start-Sleep -Milliseconds 250; try { $list = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/workers" -Headers @{ Authorization = "Bearer $token" }; if ($list.workers.machine_id -contains 'validation-worker-process') { $registered = $true; break } } catch {} }
  if (-not $registered) { throw 'worker registration timeout' }
  $headers = @{ Authorization = "Bearer $token" }
  $taskBody = @{ machine_id = 'validation-worker-process'; kind = 'shell'; payload = @{ command = 'echo worker-task-ok'; timeout = 10 } } | ConvertTo-Json -Depth 5
  $created = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$port/api/tasks" -Headers $headers -ContentType 'application/json' -Body $taskBody
  $taskId = $created.task.task_id
  if (-not $taskId) { throw 'task creation did not return task id' }
  $completed = $false
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 250
    $task = (Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/tasks/$taskId" -Headers $headers).task
    if ($task.status -in @('succeeded', 'failed', 'cancelled')) { $completed = $true; break }
  }
  if (-not $completed -or $task.status -ne 'succeeded') { throw "worker task did not succeed: $($task.status)" }
  if ($task.result.stdout -notmatch 'worker-task-ok') { throw 'worker task result missing expected output' }
  $persisted = Get-Content -Raw -LiteralPath $store | ConvertFrom-Json
  if ($persisted.tasks.$taskId.status -ne 'succeeded') { throw 'task not persisted in isolated store' }
  $timeoutBody = @{ machine_id = 'validation-worker-process'; kind = 'shell'; payload = @{ command = 'ping -n 4 127.0.0.1'; timeout = 1 } } | ConvertTo-Json -Depth 5
  $timeoutCreated = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$port/api/tasks" -Headers $headers -ContentType 'application/json' -Body $timeoutBody
  $timeoutId = $timeoutCreated.task.task_id
  $timeoutDone = $false
  for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 250
    $timeoutTask = (Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/tasks/$timeoutId" -Headers $headers).task
    if ($timeoutTask.status -in @('succeeded', 'failed', 'cancelled')) { $timeoutDone = $true; break }
  }
  if (-not $timeoutDone -or $timeoutTask.status -ne 'failed' -or $timeoutTask.result.exit_code -ne 124) { throw "worker timeout task did not fail as expected: $($timeoutTask.status)" }
  $firstSeen = ($list.workers | Where-Object machine_id -eq 'validation-worker-process').last_seen_at
  $heartbeat = $false
  for ($i = 0; $i -lt 80; $i++) {
    Start-Sleep -Milliseconds 250
    $current = (Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/workers" -Headers $headers).workers | Where-Object machine_id -eq 'validation-worker-process'
    if ($current.last_seen_at -gt $firstSeen) { $heartbeat = $true; break }
  }
  if (-not $heartbeat) { throw 'worker heartbeat did not advance' }
  Write-Output 'real worker registration, execution, timeout failure, persistence and heartbeat passed'
} finally {
  if ($worker -and -not $worker.HasExited) { Stop-Process -Id $worker.Id -Force }
  if (-not $center.HasExited) { Stop-Process -Id $center.Id -Force }
  Start-Sleep -Milliseconds 300
  if ($worker -and -not $worker.HasExited) { throw 'worker process still running' }
  if (-not $center.HasExited) { throw 'center process still running' }
  $probe = [System.Net.Sockets.TcpClient]::new()
  try {
    $probe.Connect('127.0.0.1', $port)
    throw 'validation port still listening'
  } catch [System.Net.Sockets.SocketException] {
    # Expected: owned center has released the port.
  } finally { $probe.Dispose() }
  $env:PYTHONPATH = $previousPythonPath
  Write-Output 'real worker shutdown passed'
}
