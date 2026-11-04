# Eden, Windows edition: removes what install-system.ps1 created. Run it from an elevated PowerShell:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install\uninstall.ps1 [-RemoveUserData]
# It removes the Eden firewall rules (the group "Eden"), the task "Eden helper", %ProgramFiles%\Eden and
# %ProgramData%\Eden. After this, Meshnet peers are governed by Nord's own rules again, as before Eden.
# -RemoveUserData also deletes %LOCALAPPDATA%\Eden (configuration, logs, secrets, the virtual environment).
[CmdletBinding()]
param([switch]$RemoveUserData)
$ErrorActionPreference = 'Continue'
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'eden: run this from an elevated PowerShell.' -ForegroundColor Red; exit 1
}
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*eden_winhelper.py*serve*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Stop-ScheduledTask -TaskName 'Eden helper' -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName 'Eden helper' -Confirm:$false -ErrorAction SilentlyContinue
Get-NetFirewallRule -Group 'Eden' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
foreach ($p in (Join-Path $env:ProgramFiles 'Eden'), (Join-Path $env:ProgramData 'Eden')) {
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}
if ($RemoveUserData) {
    $u = Join-Path $env:LOCALAPPDATA 'Eden'
    if (Test-Path $u) { Remove-Item -Recurse -Force $u }
}
$left = @(Get-NetFirewallRule -Group 'Eden' -ErrorAction SilentlyContinue).Count
Write-Host "eden: removed. Eden firewall rules left: $left. Stop Eden itself first if it is still running (eden.py stop)."
