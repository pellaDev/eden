<p align="center">
  <img src="webui/public/logo.svg" width="240" alt="Eden logo" />
</p>

# Eden
Eden decides which of your Nord Meshnet devices can reach which services on your computer, and nothing else.

Meshnet connects your devices, but by default every device you link can reach everything listening on your
computer. Eden turns that into a whitelist: each service (a media server, a notes app, a local AI server) is opened
only to the devices you pick, one by one, with a switch per device and per service. Everything not on the list is
closed, including after a crash: if anything fails, Eden closes everything instead of leaving a door open.

- **A local admin page** (`http://127.0.0.1:8780`, never reachable from the network) to add devices and services and
  flip the switches. English and Italian.
- **Untrusted devices.** A device can be marked untrusted: it reaches only the services you grant it. A device that
  belongs to someone else's Nord account is always untrusted.
- **A remote login** (password and one-time code) for your own devices, which opens Eden's dashboard (or a web
  service of yours that you put behind it).
- **Live traffic** per device and e-mail notifications for logins and changes.
- **On demand.** Eden runs when you start it and removes its rules when you stop it. Nothing starts at boot.

> **Status: 0.1.1, the first stable release.** Eden runs on the author's machines: Fedora Linux with Nord 6.0.2, and
> Windows 11 (build 26300) with the Nord app. These are the two machines the fixes of this release came from. The
> Windows edition is newer and has had less testing on real machines than the Linux one, so the live checks of the
> elevated helper, the scheduled task and the uninstall path are still open. Read
> [docs/security-model.md](docs/security-model.md) before you rely on it.

## Requirements

| | Linux | Windows |
|---|---|---|
| System | A recent Linux with systemd and nftables | Windows 11 |
| Nord | The Nord CLI with Meshnet (Nord 6.x tested). **The GUI app is not required** | The NordVPN app with Meshnet (there is no Nord command line on Windows) |
| Python | 3.10 or newer | 3.11 or newer, installed for all users |
| Other | `sudo`, Node 20+ and pnpm to build the web UI | none to run |

Eden does not replace the Nord app and does not route your traffic through Nord.

## Install

- Linux: [docs/linux.md](docs/linux.md) (`./install.sh`, then `./start.sh`)
- Windows: [docs/windows.md](docs/windows.md) (two PowerShell scripts, then `python windows\eden.py`)

**On Linux the Nord GUI app is not needed and it is better not to install it.** Eden only needs the Nord command line
and its daemon (`nordvpnd`): the GUI adds a tray icon, a window and a system service that Eden never uses, so leaving
it out keeps the install slim. The Nord command line works without it (`nordvpn account status`, the socket, the group).
On Windows the Nord app is required, because there is no Nord command line.

Then open `http://127.0.0.1:8780`, add a device, add a service, and give the device access to it.

**Installing with an agent:** if a model runs the installation, follow
[docs/agent-install.md](docs/agent-install.md) — it gives the exact order of the steps, the conditions to stop on, and
the difference between a fact and a guess. [AGENTS.md](AGENTS.md) at the root of the repository is the short version of
the same rules for the agent.

## How it works, in one paragraph

Your devices stay linked through Meshnet. On the Meshnet network interface Eden drops everything and then opens, for
each (device, port) pair you granted, exactly that pair: on Linux as an nftables table loaded by a small root helper,
on Windows as Windows Firewall rules created by a small elevated helper. The helper accepts only a fixed list of
commands and only ports listed in a file that only an administrator can edit, so even a bug in the web page cannot open
a port you did not allow. [docs/how-it-works.md](docs/how-it-works.md) has the details.

## Documentation

- [How it works](docs/how-it-works.md)
- [Security model and limits](docs/security-model.md)
- [Linux](docs/linux.md), [Windows](docs/windows.md)
- [Install guide for an agent](docs/agent-install.md)
- [Third-party software](docs/THIRD-PARTY.md)
- [Reporting a vulnerability](SECURITY.md)

## Development

```
pip install -r requirements.txt
python tests/run_all.py                # Linux edition
python core/test_eden_policy.py        # the policy shared by both editions
cd windows && python run_all.py                      # Windows edition: every file, one per process
cd webui && pnpm install && pnpm exec tsc --noEmit && pnpm build
```

## License

MIT, see [LICENSE](LICENSE) and [NOTICE](NOTICE). Eden is not affiliated with Nord Security.
