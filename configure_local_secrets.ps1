$ErrorActionPreference = 'Stop'

if ($env:OS -ne 'Windows_NT') { throw 'This configuration uses Windows user encryption.' }
$directory = Join-Path $PSScriptRoot '.local'
New-Item -ItemType Directory -Force -Path $directory | Out-Null
$path = Join-Path $directory 'secrets.json'
$encrypted = @{}
if (Test-Path -LiteralPath $path) {
    $existing = Get-Content -LiteralPath $path -Raw | ConvertFrom-Json
    foreach ($property in $existing.PSObject.Properties) { $encrypted[$property.Name] = $property.Value }
}
$plain = ($input | Out-String) | ConvertFrom-Json
$allowed = @('TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'ICP_NIE', 'ICP_FULL_NAME', 'ICP_NATIONALITY', 'GITHUB_TOKEN')
foreach ($property in $plain.PSObject.Properties) {
    if ($property.Name -notin $allowed) { throw 'Unsupported secret name.' }
    $secure = ConvertTo-SecureString -String ([string]$property.Value) -AsPlainText -Force
    $encrypted[$property.Name] = ConvertFrom-SecureString -SecureString $secure
}
$encrypted | ConvertTo-Json | Set-Content -LiteralPath $path -Encoding UTF8
Write-Output 'Local secrets encrypted for the current Windows user.'
