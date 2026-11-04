# Changelog

## 0.1.0 (first public pre-release, not yet tagged)

- Per-device, per-service access control on Nord Meshnet: a service's port is open only for the devices you grant it
  to, and for no one else. Devices are identified by their Meshnet key (Linux) or address (Windows), never by name.
- Linux edition: an nftables whitelist applied through a small root helper with a fixed command set.
- Windows edition (Windows 11): the same policy as Windows Firewall rules, applied by an elevated helper started on
  demand.
- Remote login (password and one-time code) that opens Eden's own dashboard, optionally in front of a web service of
  yours.
- Untrusted devices: reach only the services granted to them, never the remote login; devices of another Nord
  account are always untrusted.
- Local admin web UI on 127.0.0.1 (English and Italian), live traffic, notifications by e-mail.
