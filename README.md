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

> **Status: pre-release.** Eden works on the author's machines. The Windows edition is new and has had little
> testing. Read [docs/security-model.md](docs/security-model.md) before you rely on it.

## Requirements

| | Linux | Windows |
|---|---|---|
| System | A recent Linux with systemd and nftables | Windows 11 |
| Nord | NordVPN app with Meshnet (Nord 6.x tested) | NordVPN app with Meshnet |
| Python | 3.10 or newer | 3.11 or newer, installed for all users |
| Other | `sudo`, Node 20+ and pnpm to build the web UI | none to run |

Eden does not replace the Nord app and does not route your traffic through Nord.

## Install

- Linux: [docs/linux.md](docs/linux.md) (`./install.sh`, then `./start.sh`)
- Windows: [docs/windows.md](docs/windows.md) (two PowerShell scripts, then `python windows\eden.py`)

Then open `http://127.0.0.1:8780`, add a device, add a service, and give the device access to it.

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
- [Third-party software](docs/THIRD-PARTY.md)
- [Reporting a vulnerability](SECURITY.md)

## Development

```
pip install -r requirements.txt
python tests/run_all.py                # Linux edition
python core/test_eden_policy.py        # the policy shared by both editions
cd windows && python test_eden_winfw.py && python test_eden_winhelper.py   # Windows edition, runs on any system
cd webui && pnpm install && pnpm exec tsc --noEmit && pnpm build
```

## License

MIT, see [LICENSE](LICENSE) and [NOTICE](NOTICE). Eden is not affiliated with Nord Security.
