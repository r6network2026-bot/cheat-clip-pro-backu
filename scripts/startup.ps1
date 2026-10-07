$ErrorActionPreference = 'Stop'

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$logDirectory = Join-Path $env:LOCALAPPDATA 'CheatClipPro\logs'
$logFile = Join-Path $logDirectory 'startup.log'

New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null

function Write-StartupLog([string]$Message) {
  Add-Content -Path $logFile -Value "$(Get-Date -Format o) $Message"
}

function Test-LocalPort([int]$Port) {
  $client = [System.Net.Sockets.TcpClient]::new()
  try {
    $connection = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
    if (-not $connection.AsyncWaitHandle.WaitOne(750, $false)) {
      return $false
    }
    $client.EndConnect($connection)
    return $true
  } catch {
    return $false
  } finally {
    $client.Dispose()
  }
}

if (-not (Test-Path (Join-Path $projectRoot 'node_modules\vite\bin\vite.js'))) {
  Write-StartupLog "Dependencies are missing in $projectRoot. Run npm install before enabling startup."
  exit 1
}

$listeningPorts = @{}
foreach ($port in @(5173, 8000)) {
  $listeningPorts[$port] = Test-LocalPort $port
}

$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) {
  $npm = Get-Command npm -ErrorAction SilentlyContinue
}
if (-not $npm) {
  Write-StartupLog 'npm was not found in PATH. Install Node.js or add npm to the user PATH, then sign in again.'
  exit 1
}

$services = @(
  @{
    Port = 5173
    Name = 'frontend'
    Arguments = 'run dev-frontend -- --host 127.0.0.1'
  },
  @{
    Port = 8000
    Name = 'backend'
    Arguments = 'run dev-backend'
  }
)

foreach ($service in $services) {
  if ($listeningPorts[$service.Port]) {
    Write-StartupLog "$($service.Name) port $($service.Port) is already listening; no duplicate process started."
    continue
  }

  $stdoutLog = Join-Path $logDirectory "$($service.Name).stdout.log"
  $stderrLog = Join-Path $logDirectory "$($service.Name).stderr.log"
  try {
    $process = Start-Process `
      -FilePath $npm.Source `
      -ArgumentList $service.Arguments `
      -WorkingDirectory $projectRoot `
      -WindowStyle Hidden `
      -RedirectStandardOutput $stdoutLog `
      -RedirectStandardError $stderrLog `
      -PassThru
    Write-StartupLog "Started $($service.Name) (PID $($process.Id)) from $projectRoot."
  } catch {
    Write-StartupLog "Failed to start $($service.Name): $($_.Exception.Message)"
    exit 1
  }
}

$deadline = (Get-Date).AddSeconds(60)
do {
  foreach ($service in $services) {
    if (-not $listeningPorts[$service.Port]) {
      $listeningPorts[$service.Port] = Test-LocalPort $service.Port
    }
  }
  if (-not ($listeningPorts[5173] -and $listeningPorts[8000])) {
    Start-Sleep -Seconds 2
  }
} while (-not ($listeningPorts[5173] -and $listeningPorts[8000]) -and (Get-Date) -lt $deadline)

foreach ($service in $services) {
  if (-not $listeningPorts[$service.Port]) {
    Write-StartupLog "$($service.Name) did not become available on port $($service.Port) within 60 seconds."
    exit 1
  }
}
Write-StartupLog 'Frontend (5173) and backend (8000) are ready.'
