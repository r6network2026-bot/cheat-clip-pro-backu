$ErrorActionPreference = 'Stop'
$taskName = 'Cheat Clip PRO'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
  Write-Host 'Automatic startup has been disabled. The app is not stopped.'
} else {
  Write-Host 'Automatic startup is not configured.'
}
