#!/usr/bin/env bash
# Eden, Linux edition: removes what install.sh put outside the Eden folder: the firewall table, the root helper, the
# allowed-ports file and the sudoers rule. Stop Eden first (Ctrl+C in its terminal, or ./start.sh down).
#   ./uninstall.sh            keeps the Eden folder, its configuration and its secrets
#   ./uninstall.sh --purge    also deletes config/, data/, secrets/ and .venv inside the Eden folder
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ $EUID -ne 0 ]] || { echo "uninstall.sh: run it as your normal user." >&2; exit 1; }

HELPER=/usr/local/libexec/eden/eden_helper.py
[[ -x "$HELPER" ]] && sudo -n "$HELPER" nft-delete
sudo rm -f /etc/sudoers.d/eden
sudo rm -rf /usr/local/libexec/eden /etc/eden
if [[ "${1:-}" == "--purge" ]]; then
  rm -rf "$HERE/config" "$HERE/data" "$HERE/secrets" "$HERE/.venv"
fi
echo "Eden removed from the system. Nord's own Meshnet rules apply again."
