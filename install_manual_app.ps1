$ErrorActionPreference = 'Stop'
$taskName = 'ICPPLUS Monitor (local)'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) {
    if ($task.Actions.Arguments -notlike "*$(Join-Path $PSScriptRoot 'local_runner.ps1')*") {
        throw 'The existing task belongs to another installation; it was not changed.'
    }
    Disable-ScheduledTask -TaskName $taskName | Out-Null
    if ((Get-ScheduledTask -TaskName $taskName).State -eq 'Running') {
        Stop-ScheduledTask -TaskName $taskName
    }
}
$directory = Join-Path $PSScriptRoot '.local'
New-Item -ItemType Directory -Force -Path $directory | Out-Null
@{manual_mode=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $directory 'manual-mode.json') -Encoding UTF8
$shell = New-Object -ComObject WScript.Shell
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'ICPPLUS Monitor.lnk'
if (Test-Path -LiteralPath $shortcutPath) {
    $previousShortcut = $shell.CreateShortcut($shortcutPath)
    if ($previousShortcut.Arguments -notlike "*$(Join-Path $PSScriptRoot 'monitor_app.py')*") {
        throw 'An unrelated shortcut already uses this name; it was not replaced.'
    }
}
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
$shortcut.Arguments = '"' + (Join-Path $PSScriptRoot 'monitor_app.py') + '"'
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = 'Abrir el monitor. Iniciar y detener desde su ventana; cerrar detiene las consultas.'
$shortcut.Save()
Write-Output ('Manual application installed: ' + $shortcutPath)
