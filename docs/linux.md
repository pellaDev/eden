# Eden on Linux

## Before you start

- The NordVPN app installed and logged in, with Meshnet usable (`nordvpn meshnet peer list` works for your user).
  If your user needs the `nordvpn` group in the current session, set `NORD_USE_SG=1` in `vars.env` (see below).
- In the Nord settings, Routing, Kill Switch and Auto-connect must be off: Eden refuses to start otherwise, because
  they would change what Meshnet does. Eden switches off the notification and tray settings itself.
- Python 3.10+, `sudo`, `nft`, `systemctl`, and `pnpm` (Node 20+) to build the web UI.

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

## Run

```
./start.sh
```

Without arguments it starts everything and stays in the terminal; closing the terminal or pressing Ctrl+C stops
everything and removes the rules. Open `http://127.0.0.1:8780`. Other commands: `./start.sh up`, `down`, `vpn-up`,
`vpn-down`, `vpn-reload`, `local-up`, `local-down`, `status`.

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
