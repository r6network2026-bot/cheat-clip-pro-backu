$ErrorActionPreference = 'Stop'

$taskName = 'Cheat Clip PRO'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$startupScript = Join-Path $PSScriptRoot 'startup.ps1'
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$powershellPath = Join-Path $PSHOME 'powershell.exe'

if (-not (Test-Path (Join-Path $projectRoot 'node_modules\vite\bin\vite.js'))) {
  throw "Frontend dependencies are missing. Run 'npm install' in $projectRoot first."
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue) -and
    -not (Get-Command npm -ErrorAction SilentlyContinue)) {
  throw 'npm was not found in PATH. Install Node.js and restart this script.'
}

$arguments = "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startupScript`""
$action = New-ScheduledTaskAction `
  -Execute $powershellPath `
  -Argument $arguments `
  -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
  -StartWhenAvailable `
  -MultipleInstances IgnoreNew `
  -RestartCount 3 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
  -TaskName $taskName `
  -Action $action `
  -Trigger $trigger `
  -Principal $principal `
  -Settings $settings `
  -Description "Starts Cheat Clip PRO after $userId signs in." `
  -Force | Out-Null

Write-Host "Automatic startup is enabled for $userId."
Write-Host 'The app starts after Windows sign-in (not before sign-in).'
Write-Host "Logs: $env:LOCALAPPDATA\CheatClipPro\logs"
Write-Host "To remove it, run scripts\uninstall-startup.bat."
