# How it works

## The pieces

| Piece | Runs as | What it does |
|---|---|---|
| Eden local (`backend/eden_local.py`) | you | The admin web UI and API, on 127.0.0.1 only. Reads and writes `config/eden.json`. |
| Control (`bin/eden_ctl`, `windows/eden_winctl.py`) | you | Turns the configuration into the list of open (port, device) pairs and asks the helper to apply it. |
| Helper (`bin/eden_helper`, `windows/eden_winhelper.py`) | root / administrator | The only privileged part. Applies the firewall rules. |
| Eden remote (`bin/eden_remote`) | you | The only process listening on the Meshnet address: the login page and, after login, the dashboard. |
| Forwarder (`bin/eden_forward`) | you | Lets a service that listens only on 127.0.0.1 be reached over Meshnet, for the devices granted to it. |
| Notifications (`bin/eden_notify`) | you | E-mail alerts. Off until you configure them. |

The policy, which pairs may be open, is one small module shared by both editions (`core/eden_policy.py`), with no
dependency on the operating system.

## The policy

- A service has a port and a global switch. A device has a switch and a list of granted services.
- A pair (port, device) is open if the service is on, the device is enabled, the service is in the device's grants and
  the port is in the allowed-ports file.
- An untrusted device never gets the remote-login port. A device of another Nord account is always untrusted.
- Anything that cannot be checked (Nord not answering, a peer not found, a malformed configuration) means closed.

## The firewall

**Linux.** One nftables table, `inet eden`, replaced atomically. On the Meshnet interface it accepts replies to
connections this computer started, accepts the open pairs, drops everything else, and drops all forwarded traffic.
The root helper builds the rules itself from validated ports and addresses; nobody gives it rule text.

**Windows.** Nord's own Meshnet rule allows its peers to everything, and a Windows Block rule beats an Allow, so Eden
works with Blocks: every Meshnet address without an open port is blocked completely; an address with open ports is
blocked on every other port, on UDP and ICMP, and gets an Allow for its ports. All rules are scoped to the Meshnet
adapter and are replaced by generations (new rules first, then the old ones removed), so the machine is never less
protected during a change. When Eden is stopped, one rule blocks everything from the Meshnet adapter.

## Starting and stopping order

Start: guard (drop everything) first, then Meshnet, then the remote login and the forwarder, then the open pairs last,
so a port is open only after what listens behind it is up. Stop: close everything, stop the processes, remove the
rules.

## Devices

Linux reads the peer list from the Nord app and identifies each device by its public key. Names and addresses
are reassigned by Nord, so they are never used to decide anything. The Nord app has no command line on Windows, so there
you add each device by its Meshnet address; it starts disabled and untrusted.
