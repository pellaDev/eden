# Eden, Windows edition: the one-time system part of the installation. Run it ONCE from an elevated PowerShell:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install\install-system.ps1
# What it does (nothing else, nothing outside these places):
#   1. copies the elevated helper (2 files) to %ProgramFiles%\Eden\helper, writable by administrators only;
#   2. creates %ProgramData%\Eden (allowed_ports, helper.key), writable by administrators only;
#   3. registers the scheduled task "Eden helper": it runs the helper with the highest privileges, as YOU, only when
#      Eden asks for it (no trigger, never at boot).
# Why the helper is copied: a normal user could edit a script in a folder they own, and the helper runs elevated.
# For the same reason the Python it runs with must be one that only administrators can change.
[CmdletBinding()]
param(
    [string]$Python,          # a system-wide Python 3 (python.org "Install for all users"); found automatically if omitted
    [switch]$NewKey           # replace an existing helper.key (the running helper stops, Eden restarts it)
)
$ErrorActionPreference = 'Stop'

function Fail($text) { Write-Host "eden: $text" -ForegroundColor Red; exit 1 }
function Lock($path, $extra) {
    # Administrators and SYSTEM: full control. Users: read and run only. Inheritance from the parent is cut.
    & icacls.exe $path /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' $extra | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "could not set permissions on $path" }
}

$me = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not ([Security.Principal.WindowsPrincipal]$me).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail 'run this from an elevated PowerShell (right click, Run as administrator).'
}
if ([Environment]::OSVersion.Version.Build -lt 22000) { Fail 'Eden for Windows needs Windows 11.' }

# --- the Python the elevated helper runs with
if (-not $Python) { $cmd = Get-Command python.exe -ErrorAction SilentlyContinue; if ($cmd) { $Python = $cmd.Source } }
if (-not $Python -or -not (Test-Path $Python)) { Fail 'Python 3 was not found. Install it from python.org with "Install for all users", or pass -Python <path to python.exe>.' }
$Python = (Resolve-Path $Python).Path
$userAreas = @($env:USERPROFILE, $env:LOCALAPPDATA, $env:APPDATA, $env:TEMP) | Where-Object { $_ }
foreach ($area in $userAreas) {
    if ($Python.StartsWith($area, [StringComparison]::OrdinalIgnoreCase)) {
        Fail "this Python lives in a folder you can edit ($Python): an elevated process must not run from it. Install Python for all users (python.org, 'Install for all users') and run this script again."
    }
}
if ($Python -like '*\WindowsApps\*') { Fail 'the Microsoft Store Python cannot be used here: install Python from python.org for all users.' }
$ver = & $Python -c 'import sys; print("%d.%d" % sys.version_info[:2])'
if ([version]$ver -lt [version]'3.11') { Fail "Python $ver is too old: 3.11 or newer is needed." }
$pythonw = Join-Path (Split-Path $Python) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { $pythonw = $Python }

# --- the helper's own folder
$source = Split-Path $PSScriptRoot -Parent          # the windows\ folder of this Eden tree
$helperDir = Join-Path $env:ProgramFiles 'Eden\helper'
New-Item -ItemType Directory -Force -Path $helperDir | Out-Null
foreach ($f in 'eden_winhelper.py', 'eden_winfw.py') {
    if (-not (Test-Path (Join-Path $source $f))) { Fail "$f not found next to this script's folder ($source)." }
}
# A running helper keeps the old files in use: stop it first (it is started again on demand).
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*eden_winhelper.py*serve*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
foreach ($f in 'eden_winhelper.py', 'eden_winfw.py') { Copy-Item -Force (Join-Path $source $f) (Join-Path $helperDir $f) }
Lock (Split-Path $helperDir -Parent) '*S-1-5-32-545:(OI)(CI)RX'

# --- data folder: the ports Eden may open, and the secret of the pipe
$data = Join-Path $env:ProgramData 'Eden'
New-Item -ItemType Directory -Force -Path $data | Out-Null
Lock $data '*S-1-5-32-545:(OI)(CI)RX'
$ports = Join-Path $data 'allowed_ports'
if (-not (Test-Path $ports)) {
    Set-Content -Path $ports -Encoding ascii -Value @('# Ports Eden may open to Meshnet devices, one per line.', '# Edit this file as administrator (Eden: Services, "Open file").', '8443')
}
$keyFile = Join-Path $data 'helper.key'
if ($NewKey -or -not (Test-Path $keyFile)) {
    $bytes = New-Object byte[] 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    Set-Content -Path $keyFile -Encoding ascii -NoNewline -Value (($bytes | ForEach-Object { $_.ToString('x2') }) -join '')
}
# Only SYSTEM, administrators and the installing user may read the key.
& icacls.exe $keyFile /inheritance:r /grant:r '*S-1-5-18:F' '*S-1-5-32-544:F' "*$($me.User.Value):R" | Out-Null
if ($LASTEXITCODE -ne 0) { Fail 'could not set permissions on helper.key' }
# The ports file must not be writable by the user (the helper refuses it otherwise); the folder lock above covers it.

# --- the on-demand task
$taskName = 'Eden helper'
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"{0}" serve' -f (Join-Path $helperDir 'eden_winhelper.py')) -WorkingDirectory $helperDir
$principal = New-ScheduledTaskPrincipal -UserId $me.Name -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Description 'Eden: applies the Meshnet firewall rules. Started by Eden on demand.' | Out-Null

# --- check: start it once and ask it
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 3
$answer = & $Python -c "import sys; sys.path.insert(0, r'$source'); import eden_winclient as c; print(c.call('ping', starter=lambda: False))" 2>&1
Write-Host "helper answer: $answer"
if ("$answer" -notmatch "'ok': True") { Fail 'the helper did not answer. Look at C:\ProgramData\Eden\helper.log and the task "Eden helper" in Task Scheduler.' }
Write-Host 'eden: system part installed. Now run install\install-user.ps1 as a normal user (not elevated).' -ForegroundColor Green
