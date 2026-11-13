# Changelog

## 0.1.1 - the first stable release (2026-11-13)

The fixes from the two first real installs. `0.1.0` went out as a pre-release on 2026-11-04; this is the first release marked **stable**, and it is the version the documentation describes.

### Fixes from the first real installs (feedback, confirmed against the code and the tests)

- `start.sh` used `pgrep -q`, which procps-ng 4.0.6 does not accept: the output is redirected instead, which works on
  every version.
- `eden_ctl` stopped with an error when the configuration had no enabled device, which made the first run impossible:
  it now loads the guard table alone and says that nothing is exposed yet. A device cannot be reached before it is
  enabled, so the first-run order is documented (page first, then the guard).
- The Windows helper, checked against the seven defects reported by the first install: the transport family is chosen by platform, not hard-coded to
  `AF_UNIX`; `helper.key` is checked with the same ACL rule as the ports file, through an injectable `icacls`; the ACL
  check no longer depends on English words, it reads the shape of each access rule; the guard path refuses to act when
  no Meshnet adapter is present instead of guessing a name (the old default name is gone); the key is read inside the
  fail-closed try, and a broken request answers with an error instead of killing the listener.
- `vpn_down()` no longer reports success when the guard rules were not applied: it says the rules may still be open and
  reports a failure.
- The ceiling on the pairs is now one shared number (`core/eden_policy.py`, 32) and a test checks that both editions
  state the same value.
- The Windows install scripts: the cheap checks run before the elevation check, a machine-wide Python is looked for
  before the one on `PATH`, and an explicit `-Python <path>` is accepted; the per-user script checks the version and
  explains the same distinction.
- The Windows test runners report a failure and exit non-zero instead of printing only the passes, and the web UI now
  warns where a device is identified by an address that Nord can reassign.
- `AGENTS.md` and `docs/agent-install.md` for an agent doing the install, a `.gitignore`, and the documentation
  corrected: the Nord GUI app is not required on Linux (and better not installed), the `groupadd` message is Nord's and
  not Eden's, the Meshnet-before-Routing order, the pnpm 10 build-script warning, and what the Windows tests can and
  cannot check.
- The CI job for the Windows edition runs `windows/run_all.py`, so a failure prints a summary instead of stopping at the first file.

## 0.1.0 - pre-release, published 2026-11-04

First public commit `8af4184` (the commit named Eden 0.1.0), tag `v0.1.0`, repository `pellaDev/eden`. The repository was created 2026-11-04 and the first push went through CI on 2026-11-05, all jobs green. This is the version the first Windows install was run against.

### What it does

- Per-device, per-service access control on Nord Meshnet: a service's port is open only for the devices you grant it
  to, and for no one else. Devices are identified by their Meshnet key (Linux) or address (Windows), never by name.
- Linux edition: an nftables whitelist applied through a small root helper with a fixed command set.
- Windows edition (Windows 11): the same policy as Windows Firewall rules, applied by an elevated helper started on
  demand.
- Remote login (password and one-time code) that opens Eden's own dashboard, optionally in front of a web service of
  yours.
- Untrusted devices: reach only the services granted to them, never the remote login; devices of another Nord account
  are always untrusted.
- Local admin web UI on 127.0.0.1 (English and Italian), live traffic, notifications by e-mail.
