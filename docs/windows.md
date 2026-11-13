# Eden on Windows

Windows 11 only. The Windows edition is newer than the Linux one: it has been installed and run on one Windows 11
machine, and the tests here check its logic with fakes, not what Windows really does. The live checks on a real machine
(one firewall, one adapter, one user) are still the reference for this edition — see "What the tests do not cover".

If an agent is doing the install, read [agent-install.md](agent-install.md) before running anything.

## Before you start

- The NordVPN app installed and logged in, Meshnet turned on in the app. Eden does not turn Meshnet on or off on
  Windows (the app has no command line for it); it waits for the Meshnet adapter to appear.
- Python 3.11 or newer installed **for all users** (python.org, "Install for all users"). The elevated helper runs with
  this Python, so it must be one that only administrators can change: the install script refuses a Python under your
  user profile and the Microsoft Store one.
  The script looks for a machine-wide Python under `C:\Program Files\Python*` first, then the one on `PATH`, and accepts
  an explicit path with `-Python <path>`. On a single-user machine the one on `PATH` is usually the per-user install, so
  passing `-Python` is normal, not a workaround.
  The cheap checks (Windows build, which Python, its version) run before the elevation check, so a wrong Python is
  reported in the same run that tells you to elevate — fix both before running it again.

## Install

Two scripts, from the Eden folder.

1. In an **administrator** PowerShell, once:

```
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\install\install-system.ps1
```

It copies the helper to `%ProgramFiles%\Eden\helper` (writable by administrators only), creates `%ProgramData%\Eden`
(`allowed_ports`, `helper.key`), registers the scheduled task `Eden helper` (your user, highest privileges, started on
demand, never at boot) and checks that the helper answers.

2. In a **normal** PowerShell:

```
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\install\install-user.ps1
```

It creates a virtual environment in `%LOCALAPPDATA%\Eden\venv` and installs `windows\requirements-windows.txt`. Here a
per-user Python is fine — this environment belongs to you, unlike the one the elevated helper uses. Pass it with
`-Python <path>` when the one on `PATH` is not the one you want.

Then build the web UI once (`cd webui; pnpm install; pnpm build`) if `webui\dist` is not there. pnpm 10 and newer refuse
to run a package's build scripts by default, so `pnpm install` can end with a warning listing `esbuild`, `sharp`,
`unrs-resolver` and `workerd`: the warning is normal and not a failed install. Run `pnpm approve-builds` only when a
build really fails because of them.

`EDEN_WIN_DATA` is read by the helper from **the helper's own environment**, not from the caller's: setting it in your
shell changes where the client looks for `helper.key` but not where the helper writes its files. The two must agree, so
set it in the task's environment (or leave the default) rather than only in your shell.

## Run

```
%LOCALAPPDATA%\Eden\venv\Scripts\python.exe windows\eden.py
```

It stays in the window; closing the window or pressing Ctrl+C stops Eden and leaves the Meshnet adapter blocked. Open
`http://127.0.0.1:8780`. Other commands: `eden.py up`, `down`, `vpn-up`, `vpn-down`, `vpn-reload`, `status`.

## Add a device

Windows cannot list your Meshnet devices, so in Devices you type the device's Meshnet address (`100.x.x.x`, shown in
the Nord app). The device starts disabled and untrusted. Then give it services on the Services page.

This address is the whole identity of the device on Windows, and Nord can give a device a different address later: when
that happens the rules still point at the old number and the device stops working. The page says it when a device is
identified this way; if a device stops answering, check its address in the Nord app first.

## Allow a port

Eden never opens a port that is not listed in `%ProgramData%\Eden\allowed_ports`, one per line. The service card has an
"Open file" button that opens the file in Notepad as administrator; save it and switch the service on.

## Uninstall

In an administrator PowerShell:

```
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows\install\uninstall.ps1
```

It stops the helper and removes the task, the firewall rules (group `Eden`) and `%ProgramFiles%\Eden` and
`%ProgramData%\Eden`. Add `-RemoveUserData` to delete `%LOCALAPPDATA%\Eden` too. After it, Nord's own rules govern
Meshnet again.

## What the tests do not cover

`python run_all.py` in this folder runs the whole Windows suite on any system, because the platform parts are faked: a
fake firewall, an injectable `icacls`, the local transport of the machine running them. What a fake cannot show is what
a real Windows does:

- whether Windows Firewall really applies the rules, and whether the guard rules are still in place when Eden stops
  without a clean `down`;
- whether the scheduled task starts with the privileges it was registered with, and whether `helper.key` is readable
  only by the accounts the install granted;
- whether the Nord adapter keeps its address over time.

On these points Eden is written to report what it actually did, never what it assumed: when the guard rules are not
applied, the launcher says so and reports a failure, and the helper refuses to act when it cannot identify the Meshnet
adapter instead of guessing one. A false claim about the guard state is treated as the most dangerous kind of defect here.
