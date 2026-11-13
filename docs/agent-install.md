# Install guide for an agent

This page is written for a model that runs the installation on someone's machine. It assumes you have a shell on that
machine, the Eden files, and the user's Nord account already created. The two platform pages
([linux.md](linux.md), [windows.md](windows.md)) hold the normal instructions; this page is the order, the stop
conditions, and the difference between what you checked and what you assumed.

The root [AGENTS.md](../AGENTS.md) is the short version of the same rules.

## Rules that hold on every machine

1. Read the platform page for this machine before running anything, then follow it in order. Do not improvise a step.
2. **Stop at the first `FAILED` line.** Do not continue "to see what happens". A half-installed helper, a half-applied
   guard table, or a task that starts with the wrong privileges is worse than nothing installed. Report the failure and
   wait.
3. Never start `nordvpnd` by hand, never restart it as a way to "fix" a group problem, and never run the helper with a
   different interpreter, from a copy, or with a different key file. The helper is the only part that can open a port,
   and it only works as installed.
4. Say what you verified and what you inferred, separately. A command that returned 0 proves the command ran, not that
   the firewall is right. To claim a guard state you need the actual rules (`sudo nft list table eden` on Linux,
   `Get-NetFirewallRule -Group Eden` on Windows), not the exit code.
5. Do not open a port, add a device, create a service, or write `config/eden.json`, `secrets/`, or `vars.env` unless
   the user asked for that specific thing. Eden's defaults are part of the security model.
6. On Linux do not install the Nord GUI app: it is not needed and the user asked for a slim install. The Nord command
   line, its daemon, and the group are enough.

## The Nord order that cannot be changed

- Log in to Nord first, then open a new session (log out and in, or reboot): group membership does not apply to the
  session that created it.
- Meshnet on **before** Routing. Routing, Kill Switch, and Auto-connect must be off while Eden runs — Eden refuses to
  start otherwise.
- Routing on with Meshnet off breaks every Meshnet inbound connection. If a device cannot reach anything, check this
  pair of settings before anything else.

## Linux, in order

1. Check before installing: `nordvpn account status`, `nordvpn meshnet peer list` as the user, the `nordvpn` group,
   `python3` 3.10+, `nft`, `systemctl`, `node` 20+ and `pnpm`. Set `NORD_USE_SG=1` in `vars.env` only if the
   group is needed in the current session.
2. `./install.sh`, as the normal user. A message about `groupadd` is the Nord installer's own message, not Eden's: it
   means the user was not in the group at that moment. It is not an Eden failure.
3. A `pnpm install` warning listing build scripts (`esbuild`, `sharp`, `unrs-resolver`, `workerd`) is normal on
   pnpm 10+. It is not a failed install. Approve those builds only if a build actually fails because of them.
4. `./start.sh local-up`: the admin page alone, nothing on the firewall. Add the device and the service in the page,
   enable the device, grant the service.
5. Then `./start.sh`. On an empty configuration the correct behaviour is the guard table alone, with a line saying no
   enabled device was resolved: everything on the Meshnet interface is dropped, nothing is exposed. `vpn-up` needs at
   least one enabled device — that is not a deadlock, it is the order.

## Windows, in order

1. `install\install-system.ps1`, once, from an elevated PowerShell. It reports the cheap problems (Windows build, which
   Python, its version) before the elevation one, so fix both in one run. It looks for a machine-wide Python under
   `C:\Program Files\Python*` first, then `PATH`; on a single-user machine the one on `PATH` is usually the per-user
   install and is refused on purpose — pass `-Python <path>` with the all-users install.
2. `install\install-user.ps1`, as a normal user. Here a per-user Python is fine.
3. Run with the venv: `%LOCALAPPDATA%\Eden\venv\Scripts\python.exe windows\eden.py`. Build the web UI once if
   `webui\dist` is missing.
4. `EDEN_WIN_DATA` is read from the **helper's** environment, not the caller's: setting it in your shell moves where the
   client looks for `helper.key` but not where the helper works. Set it in the task, or leave the default.

## Stop conditions

Stop and report when:

- any step prints `FAILED`;
- the permission check on `helper.key` or on the helper's folder fails, or you cannot read what the check said (an
  `icacls` summary line is not an access rule — do not read the language, read the shape);
- the helper refuses to identify the Meshnet adapter. Do not guess an adapter name; the refusal is the answer;
- a device's address cannot be confirmed from the Nord app on Windows: on Windows the address is the device's identity,
  and an address that Nord reassigns stops the device;
- the admin page shows a network error while you turn the VPN on: look at the terminal first. In most cases the request
  was killed because a step failed and Eden tore everything down, not because the page is broken;
- the machine is not the one the user described (different OS, different user, different Nord account).

## Before saying "installed"

A completed install means, and only means: every step ran with exit code 0, the helper answered `ping`, the rule list
you read matches what Eden said it applied, and `nordvpn meshnet peer list` works for the user. Anything else is a
report, not a confirmation: state which of these you actually ran, in the user's language, and keep the inferred parts
clearly apart from the verified ones.
