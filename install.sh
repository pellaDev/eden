#!/usr/bin/env bash
# Eden, Linux edition: installation. Run it as your normal user from the Eden folder (it asks for sudo only for the
# root part):   ./install.sh
# What it does:
#   1. checks the tools Eden needs;
#   2. creates a virtual environment (.venv) and installs requirements.txt;
#   3. creates config/eden.json from config/eden.example.json when there is none (no device, no service);
#   4. installs the root helper to /usr/local/libexec/eden (root-owned), the allowed-ports file /etc/eden/allowed_ports
#      (8443 only, when there is none) and /etc/sudoers.d/eden, which lets YOUR user run that one helper without a
#      password and nothing else; the rule is checked with visudo before it is installed;
#   5. builds the web UI when pnpm is available and webui/dist is missing.
# Nothing else outside this folder is touched. uninstall.sh reverses the root part.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

fail() { echo "install.sh: $*" >&2; exit 1; }
[[ $EUID -ne 0 ]] || fail "run it as your normal user, not as root (it uses sudo for the root part)."
USER_NAME="$(id -un)"
[[ "$USER_NAME" =~ ^[a-z_][a-z0-9_-]*$ ]] || fail "the user name '$USER_NAME' cannot be used in a sudoers rule."

# --- 1. tools
command -v python3 >/dev/null || fail "python3 is missing."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || fail "Python 3.10 or newer is needed."
python3 -c 'import venv' 2>/dev/null || fail "the python3 venv module is missing (Debian/Ubuntu: sudo apt install python3-venv)."
for tool in sudo visudo nft systemctl; do
  command -v "$tool" >/dev/null || [[ -x /usr/sbin/$tool ]] || fail "$tool is missing."
done
command -v nordvpn >/dev/null || echo "install.sh: warning: the nordvpn command was not found; install NordVPN before starting Eden."

# --- 2. virtual environment
VENV="${EDEN_VENV:-$HERE/.venv}"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r requirements.txt

# --- 3. configuration
mkdir -p config
[[ -f config/eden.json ]] || cp config/eden.example.json config/eden.json

# --- 4. root part
HELPER_SRC="$HERE/bin/eden_helper/eden_helper.py"
[[ -f "$HELPER_SRC" ]] || fail "$HELPER_SRC not found."
HELPER_DST=/usr/local/libexec/eden/eden_helper.py
sudo install -d -m 755 -o root -g root /etc/eden /usr/local/libexec/eden
if [[ ! -e /etc/eden/allowed_ports ]]; then
  printf '# Ports Eden may open to Meshnet devices, one per line. Edit with sudo.\n8443\n' | sudo tee /etc/eden/allowed_ports >/dev/null
  sudo chmod 644 /etc/eden/allowed_ports
  sudo chown root:root /etc/eden/allowed_ports
fi
sudo install -m 755 -o root -g root "$HELPER_SRC" "$HELPER_DST"
RULE="$(mktemp)"
trap 'rm -f "$RULE"' EXIT
echo "$USER_NAME ALL=(root) NOPASSWD: $HELPER_DST" >"$RULE"
sudo visudo -cf "$RULE" >/dev/null || fail "the sudoers rule did not validate; nothing was installed."
sudo install -m 440 -o root -g root "$RULE" /etc/sudoers.d/eden
sudo -n "$HELPER_DST" ports-list >/dev/null || fail "the helper does not answer through sudo."

# --- 5. web UI
if [[ ! -d webui/dist && -f webui/package.json ]]; then
  if command -v pnpm >/dev/null; then
    (cd webui && pnpm install --frozen-lockfile && pnpm build)
  else
    echo "install.sh: warning: pnpm was not found and webui/dist is missing: install pnpm, then run  cd webui && pnpm install && pnpm build"
  fi
fi

echo "Eden is installed. Start it with:  ./start.sh   then open http://127.0.0.1:8780/"
