# Eden on Windows

Windows 11 only. The Windows edition is new and has had little testing.

## Before you start

- The NordVPN app installed and logged in, Meshnet turned on in the app. Eden does not turn Meshnet on or off on
  Windows (the app has no command line for it); it waits for the Meshnet adapter to appear.
- Python 3.11 or newer installed **for all users** (python.org, "Install for all users"). The elevated helper runs with
  this Python, so it must be one that only administrators can change: the install script refuses a Python under your
  user profile and the Microsoft Store one.

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

It creates a virtual environment in `%LOCALAPPDATA%\Eden\venv` and installs `windows\requirements-windows.txt`. Then
build the web UI once (`cd webui; pnpm install; pnpm build`) if `webui\dist` is not there.

## Run

```
%LOCALAPPDATA%\Eden\venv\Scripts\python.exe windows\eden.py
```

It stays in the window; closing the window or pressing Ctrl+C stops Eden and leaves the Meshnet adapter blocked. Open
`http://127.0.0.1:8780`. Other commands: `eden.py up`, `down`, `vpn-up`, `vpn-down`, `vpn-reload`, `status`.

## Add a device

Windows cannot list your Meshnet devices, so in Devices you type the device's Meshnet address (`100.x.x.x`, shown in
the Nord app). The device starts disabled and untrusted. Then give it services on the Services page.

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
