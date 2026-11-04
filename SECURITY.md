# Security policy

Eden controls what can reach your computer, so security reports are welcome and taken seriously.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's **private vulnerability reporting** on this repository (Security tab,
"Report a vulnerability"). Include the version (`VERSION`), your system, and the steps to reproduce.

This is a one-person project: expect an answer within a few days, not hours.

## What counts

Eden's promise is narrow: *a device can reach a port of this computer over Meshnet only if you granted that
(device, port) pair, and a failure closes everything.* Reports that break that promise are the most valuable:

- a port reachable by a device that has no grant for it;
- a way for the local web page, the remote login or a Meshnet device to make the root or elevated helper open a port
  that is not in the allowed-ports file, or run anything else;
- a way around the remote login (password and one-time code);
- the helper leaving rules in place after a failure (it must fail closed).

The known limits are listed in [docs/security-model.md](docs/security-model.md); they are not vulnerabilities.

## Supported versions

Only the latest release.
