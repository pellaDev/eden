# Eden on Linux

## Before you start

- The Nord **command line** installed and logged in, with Meshnet usable (`nordvpn meshnet peer list` works for your
  user). The Nord GUI app is **not required on Linux and it is better not to install it**: Eden uses only the `nordvpn`
  command, its daemon (`nordvpnd`) and the socket, never a window or a tray icon. The command line works on its own, and
  `nordvpn_install.sh --no-configure` is the way to install just that.
  If your user needs the `nordvpn` group in the current session, set `NORD_USE_SG=1` in `vars.env` (see below).
- After the Nord install, log out and back in (or reboot): the group membership only takes effect in a new session.
  Check `nordvpn account status` before running `./install.sh`.
- In the Nord settings, Routing, Kill Switch and Auto-connect must be off: Eden refuses to start otherwise, because
  they would change what Meshnet does. Eden switches off the notification and tray settings itself.
  Order matters when Nord is set up: Meshnet on first, Routing after. Routing must stay off while Eden runs — with
  Routing on and Meshnet off, nothing from Meshnet reaches this computer.
- Python 3.10+, `sudo`, `nft`, `systemctl`, and `pnpm` (Node 20+) to build the web UI.

If an agent is doing the install, read [agent-install.md](agent-install.md) before running anything.

## What Eden owns

Eden starts and stops `nordvpnd` by itself. While Eden is down, `nordvpn` commands fail with the missing-socket
message: that is the expected behaviour, not a broken install, and the daemon must not be started by hand.

Eden owns the Meshnet side. It never runs `nordvpn set meshnet`, never connects or disconnects a peer, never edits a
peer's permissions. The login, the account and the settings named above stay with the user. Eden filters only the
Meshnet interface: nothing is added on the local network to "complete" it, and the LAN is not protected by Eden.

## Install

```
./install.sh
```

It runs as your normal user and uses `sudo` for the root part only:

1. creates `.venv` and installs `requirements.txt`;
2. creates `config/eden.json` from `config/eden.example.json` (no device, no service);
3. installs the root helper to `/usr/local/libexec/eden/` (root-owned), `/etc/eden/allowed_ports` (only 8443) and
   `/etc/sudoers.d/eden`, which lets your user run that one helper without a password and nothing else (the rule is
   checked with `visudo` before it is installed);
4. builds the web UI with `pnpm` when `webui/dist` is missing.

Two things worth knowing about this step:

- A message about `groupadd` coming from the Nord installer is Nord's own message, not an Eden one: it only says your
  user was not in the `nordvpn` group at that moment. It is not an Eden failure and nothing in Eden needs changing —
  the fix is the new session above.
- pnpm 10 and newer refuse to run a package's build scripts by default, so `pnpm install` can end with a warning
  listing `esbuild`, `sharp`, `unrs-resolver` and `workerd`. The warning is normal and is not a failed install: the web
  UI builds without those scripts. Run `pnpm approve-builds` only when a build really fails because of them.

## Run

```
./start.sh
```

Without arguments it starts everything and stays in the terminal; closing the terminal or pressing Ctrl+C stops
everything and removes the rules. Open `http://127.0.0.1:8780`. Other commands: `./start.sh up`, `down`, `vpn-up`,
`vpn-down`, `vpn-reload`, `local-up`, `local-down`, `status`.

**First run, in this order:** log in to Nord, reboot, `./install.sh`, then `./start.sh local-up` (the admin page alone,
nothing on the firewall yet), add a device and a service in the page, and only then `./start.sh`. With an empty
configuration there is nothing to open: `./start.sh` loads the guard table only — every address on the Meshnet
interface is dropped — and says that no device is enabled yet. That is not an error, but a device cannot be reached
before it is enabled, and `vpn-up` needs at least one enabled device.

## Allow a port

Eden never opens a port that is not listed in `/etc/eden/allowed_ports`, one port per line (`#` starts a comment),
edited with `sudo`. The service card shows a warning and an "Open file" button when a port is missing. Add the port,
then switch the service on.

## Remote login

In Settings, open an enrollment window to set the password and scan the one-time-code QR with an authenticator app.
Without it, the remote login stays closed.

## Configuration

Everything has a default inside the Eden folder. To change a path or a port, copy `vars.env.example` to `vars.env`
and uncomment what you need (`EDEN_CONFIG`, `EDEN_SECRETS`, `EDEN_LOCAL_PORT`, `EDEN_UPSTREAM_PORT`, ...).
`EDEN_UPSTREAM_PORT` is a web service on 127.0.0.1 that a logged-in remote user is forwarded to; empty means the
user is sent to Eden's dashboard.

## Update

Replace the files, run `./install.sh` again (it reinstalls the helper), rebuild the web UI if `webui/` changed
(`cd webui && pnpm install && pnpm build`) and restart Eden.

## Uninstall

```
./uninstall.sh            # removes the firewall table, the helper, the allowed-ports file and the sudoers rule
./uninstall.sh --purge    # also deletes config/, data/, secrets/ and .venv
```
