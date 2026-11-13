# Eden, Windows edition: the per-user part of the installation. Run it as a NORMAL user (not elevated), after
# install-system.ps1:
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\install\install-user.ps1
# It creates a virtual environment in %LOCALAPPDATA%\Eden\venv and installs the packages of requirements-windows.txt.
# Then start Eden with:   %LOCALAPPDATA%\Eden\venv\Scripts\python.exe windows\eden.py
[CmdletBinding()]
param([string]$Python)
$ErrorActionPreference = 'Stop'
function Fail($text) { Write-Host "eden: $text" -ForegroundColor Red; exit 1 }

# The cheap checks first: here a per-user Python is fine (this environment belongs to the user, unlike the one the
# elevated helper uses), so the usual problem is a missing or too old Python and that is worth saying before anything
# else, in the same run.
if (-not $Python) { $cmd = Get-Command python.exe -ErrorAction SilentlyContinue; if ($cmd) { $Python = $cmd.Source } }
if (-not $Python) { Fail 'Python 3.11 or newer was not found. Pass it with -Python <path to python.exe>.' }
$ver = & $Python -c 'import sys; print("%d.%d" % sys.version_info[:2])'
if ([version]$ver -lt [version]'3.11') { Fail "Python $ver is too old: 3.11 or newer is needed." }

if (([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail 'run this as a normal user, not elevated: the environment must belong to you.'
}
$venv = Join-Path $env:LOCALAPPDATA 'Eden\venv'
& $Python -m venv $venv
if ($LASTEXITCODE -ne 0) { Fail 'could not create the virtual environment.' }
$venvPython = Join-Path $venv 'Scripts\python.exe'
$requirements = Join-Path (Split-Path $PSScriptRoot -Parent) 'requirements-windows.txt'
& $venvPython -m pip install --upgrade pip | Out-Null
& $venvPython -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) { Fail 'could not install the packages.' }
Write-Host "eden: installed. Start Eden with:  & '$venvPython' '$(Join-Path (Split-Path $PSScriptRoot -Parent) 'eden.py')'" -ForegroundColor Green
