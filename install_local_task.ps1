$ErrorActionPreference = 'Stop'
$taskName = 'ICPPLUS Monitor (local)'
$runner = Join-Path $PSScriptRoot 'local_runner.ps1'
$powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing -and ($existing.Actions.Arguments -notlike "*$runner*")) {
    throw 'A different task already uses this name; it was not changed.'
}
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$nextStart = & $python -c 'from datetime import datetime,timezone; from quarter_schedule import next_preparation_time; print(next_preparation_time(datetime.now(timezone.utc)).isoformat())'
if ($LASTEXITCODE -ne 0) { throw 'Could not calculate the next preparation time.' }
$nextStartTime = [DateTimeOffset]::Parse($nextStart)
$action = New-ScheduledTaskAction -Execute $powershell -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -File "' + $runner + '" -QuarterHour') -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Once -At $nextStartTime.LocalDateTime -RepetitionInterval (New-TimeSpan -Minutes 15)
$trigger.StartBoundary = $nextStartTime.UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ss'Z'")
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Select-Object TaskName, State
Write-Output ('Preparation starts at ' + $nextStartTime.ToLocalTime().ToString('HH:mm:ss') + ', then every 15 minutes. Availability requests are held until :00, :15, :30 or :45.')
