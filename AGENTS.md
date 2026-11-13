# Instructions for an agent working on Eden

If you are a model reading this because you were asked to **install** Eden on a machine, the full procedure is
[docs/agent-install.md](docs/agent-install.md): the order of the steps, the stop conditions, and the report format. Read
it before running anything. These are the rules that do not change in any case:

- Stop at the first `FAILED` line. A half-installed helper or a half-applied guard table is more dangerous than an
  uninstalled one.
- On Linux the Nord GUI app is not needed and should not be installed: the Nord command line, `nordvpnd`, and the group
  are enough. Never start `nordvpnd` by hand.
- Nord order: Meshnet on **before** Routing. Routing, Kill Switch, and Auto-connect stay off while Eden runs. Routing on
  with Meshnet off breaks every Meshnet inbound connection.
- Nothing opens a port except the helper, and only for ports in the allowed-ports file. Do not add devices, services,
  ports, config, or secrets on the user's behalf unless asked.
- A command returning 0 proves the command ran, not that the firewall is right. To claim a guard state, read the actual
  rules (`sudo nft list table eden`, `Get-NetFirewallRule -Group Eden`.
- Keep verified facts apart from inferences in every report. If you cannot read something, say so instead of assuming.

If you are working on the code instead of installing it: the policy shared by the two editions is in
`core/eden_policy.py` and its tests in `core/test_eden_policy.py`; the Windows tests use fakes for the platform so they
run on any system, and `run_all.py` in each test folder prints one line per file and exits non-zero on any failure.
