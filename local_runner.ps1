param(
    [switch]$Probe,
    [switch]$TestTelegram,
    [switch]$NoPublish,
    [switch]$QuarterHour,
    [switch]$FromApp
)

$ErrorActionPreference = 'Stop'
$directory = Join-Path $PSScriptRoot '.local'
if ((Test-Path -LiteralPath (Join-Path $directory 'manual-mode.json')) -and -not $FromApp -and -not $Probe -and -not $TestTelegram) {
    Write-Error 'El inicio automático está desactivado. Abre ICPPLUS Monitor y pulsa Iniciar.'
    exit 1
}
New-Item -ItemType Directory -Force -Path $directory | Out-Null
$lock = $null
try {
    $lock = [System.IO.File]::Open((Join-Path $directory 'run.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
} catch [System.IO.IOException] {
    Write-Output 'A local check is already running.'
    exit 0
}

$log = Join-Path $directory 'monitor.log'
try {
    $secretPath = Join-Path $directory 'secrets.json'
    if (Test-Path -LiteralPath $secretPath) {
        $encrypted = Get-Content -LiteralPath $secretPath -Raw | ConvertFrom-Json
        foreach ($property in $encrypted.PSObject.Properties) {
            $secure = ConvertTo-SecureString -String $property.Value
            $pointer = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
            try {
                [Environment]::SetEnvironmentVariable($property.Name, [System.Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer), 'Process')
            } finally {
                [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
            }
        }
    }
    Set-Location -LiteralPath $PSScriptRoot
    $env:SE_CACHE_PATH = Join-Path $PSScriptRoot '.cache\selenium'
    $env:TEMP = Join-Path $PSScriptRoot '.cache\tmp'
    $env:TMP = $env:TEMP
    $env:PYTHONIOENCODING = 'utf-8'
    $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    [Console]::OutputEncoding = $OutputEncoding
    $env:ICP_BROWSER_PROFILE = Join-Path $directory 'chrome-profile'
    New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    Add-Content -LiteralPath $log -Value ("`n=== Local check: " + (Get-Date -Format o) + ' ===') -Encoding UTF8
    $arguments = @('-u', 'monitor.py', '--headed')
    if ($QuarterHour) { $arguments += '--quarter-hour' }
    if ($Probe) { $arguments += '--probe-browser' }
    if ($TestTelegram) { $arguments += '--test-telegram' }
    $runStarted = [DateTimeOffset]::UtcNow
    & $python @arguments 2>&1 | Out-File -FilePath $log -Append -Encoding utf8
    $result = $LASTEXITCODE
    if (($Probe -or $TestTelegram) -and $result -ne 0) { throw "Monitor process exited with code $result. See .local/monitor.log." }
    if (-not $Probe -and -not $TestTelegram) {
        $status = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'data\status.json') -Raw | ConvertFrom-Json
        if ([DateTimeOffset]::Parse($status.last_run) -lt $runStarted.AddSeconds(-2)) {
            throw 'This execution did not produce a new result; the old status was not republished.'
        }
        & $python publish_dashboard.py 2>&1 | Out-File -FilePath $log -Append -Encoding utf8
        if (-not $NoPublish) {
            & $python publish_local_status.py 2>&1 | Out-File -FilePath $log -Append -Encoding utf8
            if ($LASTEXITCODE -ne 0) { throw 'The local check finished, but the web status could not be published.' }
        }
        if ($result -ne 0) { throw "The portal check did not complete (code $result). Its failure status was published. See .local/monitor.log." }
    }
    Write-Output 'Local run completed. Details: .local/monitor.log'
} catch {
    Add-Content -LiteralPath $log -Value $_.Exception.Message -Encoding UTF8
    Write-Error $_.Exception.Message
    exit 1
} finally {
    foreach ($key in @('TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'ICP_NIE', 'ICP_FULL_NAME', 'ICP_NATIONALITY', 'GITHUB_TOKEN')) {
        [Environment]::SetEnvironmentVariable($key, $null, 'Process')
    }
    if ($lock) { $lock.Dispose() }
}
