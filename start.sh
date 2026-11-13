#!/usr/bin/env bash
# Eden launcher (Linux edition). Two independent groups plus a combined convenience command:
#   vpn-up | vpn-down         VPN group: Nord daemon, Meshnet, nft rules, eden_remote, eden_forward
#   remote-restart            restart eden_remote only (drops every remote session)
#   vpn-reload                re-apply nft rules from eden.json while the VPN is up (no restart)
#   local-up | local-down     Eden local: loopback-only admin webUI + API (FastAPI)
#   up | down                 VPN + Eden local together, fail-closed per group (local is separate:
#                             it needs no Meshnet/Nord and is meant to stay available regardless)
#   status                    state of every managed process
#   (no argument)             foreground: start everything, tear it all down when this terminal closes
#
# Paths and tunables come from the environment or from an optional vars.env next to this file (see vars.env.example);
# anything left unset defaults to a place inside this folder.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set -a
# shellcheck disable=SC1091
[[ -f "$HERE/vars.env" ]] && source "$HERE/vars.env"
: "${EDEN_HOME:=$HERE}"
: "${EDEN_CONFIG:=$HERE/config/eden.json}"
: "${EDEN_AVATARS:=$HERE/data/avatars.json}"
: "${EDEN_RUN:=$HERE/data/run}"
: "${EDEN_LOGS:=$HERE/data/logs}"
: "${EDEN_SECRETS:=$HERE/secrets}"
: "${EDEN_VENV:=$HERE/.venv}"
: "${EDEN_HELPER:=/usr/local/libexec/eden/eden_helper.py}"
: "${EDEN_LOCAL_PORT:=8780}"
: "${MESH_IFACE:=nordlynx}"
set +a

# secrets/ may be a symlink onto an encrypted volume. Refuse to proceed on a broken link instead of silently
# creating an empty directory elsewhere.
if [[ -L "$EDEN_SECRETS" && ! -e "$EDEN_SECRETS" ]]; then
  echo "start.sh: $EDEN_SECRETS is a broken symlink - is the volume that holds it mounted?" >&2
  exit 1
fi

mkdir -p "$EDEN_RUN" "$EDEN_LOGS" "$EDEN_SECRETS" "$(dirname "$EDEN_CONFIG")"
chmod 700 "$EDEN_RUN" "$EDEN_SECRETS"

# Start a background process, record its pid under EDEN_RUN.
spawn() { # name, command...
  local name="$1"; shift
  "$@" >"$EDEN_LOGS/$name.log" 2>&1 &
  echo $! >"$EDEN_RUN/$name.pid"
}

# True if the pid file exists and the process is alive.
alive() { [[ -f "$EDEN_RUN/$1.pid" ]] && kill -0 "$(cat "$EDEN_RUN/$1.pid")" 2>/dev/null; }


status() {
  local n
  echo "-- Eden local --"
  alive eden_local && echo "eden_local: running (http://127.0.0.1:$EDEN_LOCAL_PORT/)" || echo "eden_local: stopped"
  echo "-- VPN --"
  # pgrep -q is not accepted by procps-ng 4.0.6 (only --quiet): redirect the output instead, which works on every version.
  pgrep -x nordvpnd >/dev/null && echo "nordvpnd: running" || echo "nordvpnd: stopped"
  ip -br addr show "$MESH_IFACE" &>/dev/null && echo "$MESH_IFACE: up" || echo "$MESH_IFACE: down"
  alive eden_remote && echo "eden_remote: running" || echo "eden_remote: stopped"
  alive eden_forward && echo "eden_forward: running" || echo "eden_forward: stopped"
}

# Helpers for the Nord side. Root actions only through the helper, never plain sudo.
CTL=("$EDEN_VENV/bin/python" "$HERE/bin/eden_ctl/eden_ctl.py")
helper() { sudo -n "$EDEN_HELPER" "$@"; }
nord() { # nordvpn CLI, through "sg nordvpn -c" while NORD_USE_SG=1
  if [[ "${NORD_USE_SG:-0}" == 1 ]]; then sg nordvpn -c "nordvpn $*"; else nordvpn "$@"; fi
}

# Run one step of a group; on failure, tear down only that group (fail closed
# per group, not the other one).
step_vpn() {
  "$@" || { echo "FAILED: $*" >&2; vpn_down; return 1; }
}

remote_up() {
  if alive eden_remote; then echo "eden_remote already running"; return 0; fi
  local mesh_ip
  mesh_ip="$(ip -4 -br addr show "$MESH_IFACE" | awk '{print $3}' | cut -d/ -f1)"
  [[ -n "$mesh_ip" ]] || { echo "eden_remote: no address on $MESH_IFACE, is Meshnet on?" >&2; return 1; }
  EDEN_REMOTE_BIND="$mesh_ip" spawn eden_remote "$EDEN_VENV/bin/python" "$HERE/bin/eden_remote/eden_remote.py"
  sleep 1
  alive eden_remote || { echo "eden_remote failed to start, see $EDEN_LOGS/eden_remote.log" >&2; return 1; }
  echo "eden_remote up on $mesh_ip:$(python3 -c "import json;print(json.load(open('$EDEN_CONFIG'))['remote_port'])")"
}

remote_down() {
  [[ -f "$EDEN_RUN/eden_remote.pid" ]] && kill "$(cat "$EDEN_RUN/eden_remote.pid")" 2>/dev/null
  rm -f "$EDEN_RUN/eden_remote.pid"
}

forward_up() {
  # Relay for services that listen only on 127.0.0.1: it listens on the Meshnet address, accepts only the devices
  # eden_ctl lists for each port and forwards to 127.0.0.1. Started before nft-final, so a port is never open in
  # the firewall with nothing listening behind it. It starts with no routes: eden_ctl hands them over.
  if alive eden_forward; then echo "eden_forward already running"; return 0; fi
  local mesh_ip
  mesh_ip="$(ip -4 -br addr show "$MESH_IFACE" | awk '{print $3}' | cut -d/ -f1)"
  [[ -n "$mesh_ip" ]] || { echo "eden_forward: no address on $MESH_IFACE, is Meshnet on?" >&2; return 1; }
  rm -f "$EDEN_RUN/forward.json" "$EDEN_RUN/forward.status.json"   # never start from a previous run's routes
  EDEN_FORWARD_BIND="$mesh_ip" spawn eden_forward "$EDEN_VENV/bin/python" "$HERE/bin/eden_forward/eden_forward.py"
  sleep 1
  alive eden_forward || { echo "eden_forward failed to start, see $EDEN_LOGS/eden_forward.log" >&2; return 1; }
  echo "eden_forward up on $mesh_ip"
}

forward_down() {
  [[ -f "$EDEN_RUN/eden_forward.pid" ]] && kill "$(cat "$EDEN_RUN/eden_forward.pid")" 2>/dev/null
  rm -f "$EDEN_RUN/eden_forward.pid" "$EDEN_RUN/forward.json" "$EDEN_RUN/forward.status.json"
}

notify_event() { # event id, detail...: e-mail alert through eden_notify. Fire and forget: it can never delay or fail the launcher.
  ( "$EDEN_VENV/bin/python" "$HERE/bin/eden_notify/eden_notify.py" event "$@" >>"$EDEN_LOGS/eden_notify.log" 2>&1 & )
}

local_up() {
  if alive eden_local; then echo "eden_local already running"; return 0; fi
  # Hardcoded to loopback, not read from vars.env: this admin backend must never
  # be reachable from anywhere but 127.0.0.1, regardless of configuration.
  spawn eden_local bash -c "cd '$HERE' && exec '$EDEN_VENV/bin/python' -m uvicorn backend.eden_local:app --host 127.0.0.1 --port '$EDEN_LOCAL_PORT'"
  sleep 1
  alive eden_local || { echo "eden_local failed to start, see $EDEN_LOGS/eden_local.log" >&2; return 1; }
  echo "eden_local up on http://127.0.0.1:$EDEN_LOCAL_PORT/"
}

local_down() {
  [[ -f "$EDEN_RUN/eden_local.pid" ]] && kill "$(cat "$EDEN_RUN/eden_local.pid")" 2>/dev/null
  rm -f "$EDEN_RUN/eden_local.pid"
}

meshnet_on() {
  # Idempotent: Meshnet already enabled (e.g. left on by an interrupted run) is the
  # desired state, not a failure. The nordvpn CLI returns non-zero in that case.
  local out rc
  out="$(nord set meshnet on 2>&1)"; rc=$?
  echo "$out"
  [[ $rc -eq 0 || "$out" == *"already enabled"* ]]
}

vpn_up() {
  # Order matters: guard table before Meshnet exists, remote proxy after Meshnet
  # has an address, peers allowed last (so a port is only reachable once whatever
  # is behind it is actually up).
  step_vpn "${CTL[@]}" nft-guard || return 1
  step_vpn helper daemon-start || return 1
  sleep 2
  step_vpn "${CTL[@]}" settings || return 1
  step_vpn meshnet_on || return 1
  sleep 3
  step_vpn remote_up || return 1
  step_vpn forward_up || return 1
  step_vpn "${CTL[@]}" nft-final || return 1
  step_vpn "${CTL[@]}" incoming allow || return 1
  echo "VPN up."
}

remote_restart() {
  # Restart eden_remote alone, e.g. to open an enrollment window: it keeps sessions in
  # memory only, so this logs every remote user out. Needs the VPN up (Meshnet address).
  alive eden_remote || { echo "eden_remote is not running (is the VPN up?)" >&2; return 1; }
  remote_down
  sleep 1   # let the old process release the port
  remote_up
}

vpn_down() {
  # Reverse order; every step is best effort so one failure cannot block the rest.
  "${CTL[@]}" deny-all
  remote_down
  forward_down
  nord set meshnet off
  helper daemon-stop
  helper nft-delete
  echo "== leftovers (VPN) =="
  pgrep -af 'nordvpnd|norduserd|nordfileshare'
  ip -br addr show "$MESH_IFACE" 2>&1 | head -1
  helper nft-list 2>&1
  echo "-- residual Meshnet-facing ports --"
  ss -tlnH | grep -E ":$(python3 -c "import json;print(json.load(open('$EDEN_CONFIG'))['remote_port'])" 2>/dev/null)\b"
  echo "(nothing above this line from ss = clean)"
  return 0
}

vpn_reload() {
  # Re-apply the nft rules from config/eden.json without touching the Nord daemon,
  # Meshnet or peer permissions. Only meaningful while the VPN is up; otherwise the
  # config change simply takes effect at the next vpn-up. The first output line is
  # machine-readable for eden_local ("RELOAD: applied" / "RELOAD: deferred").
  if ! ip -br addr show "$MESH_IFACE" &>/dev/null || ! helper nft-list &>/dev/null; then
    echo "RELOAD: deferred"
    echo "VPN not up: config saved, rules will be loaded at the next vpn-up."
    return 0
  fi
  # The forwarder is started by vpn_up; bring it back if it crashed or this VPN session predates it.
  alive eden_forward || forward_up || { echo "RELOAD: failed (eden_forward)" >&2; return 1; }
  # "reload" swaps the nft table atomically (on failure the previous rules stay in place)
  # and syncs each peer's Meshnet incoming permission with the enabled devices.
  "${CTL[@]}" reload || { echo "RELOAD: failed" >&2; return 1; }
  echo "RELOAD: applied"
}


up() {
  # Convenience: the VPN group and Eden local together, in one command - what a launcher or a double-click
  # shortcut should invoke. Each group still fails closed on its own; a local-UI failure after the VPN came up
  # leaves the VPN running (the groups stay independent).
  step_vpn vpn_up || return 1
  local_up || return 1
  notify_event eden_started "VPN and local interface started"
  echo "Eden up."
}

down() {
  local_down
  vpn_down
}

foreground_all() {
  # The mode for an interactive terminal: bring everything up, then sit here
  # holding the terminal. Closing the terminal (SIGHUP) or Ctrl+C (SIGINT) both
  # trigger bash's EXIT trap, which tears everything down - so Eden's lifetime
  # is tied to this one terminal, as intended. down() is best-effort/idempotent,
  # so it's safe even if a signal interrupts it partway.
  RESTART_REQUESTED=0
  RESTARTING=0
  echo $$ >"$EDEN_RUN/eden.pid"   # lets Eden local ask this process for a restart (SIGUSR1, see below)
  trap 'down; rm -f "$EDEN_RUN/eden.pid"' EXIT
  trap 'exit 0' HUP INT TERM   # force a controlled exit for every way this terminal can go away,
                               # so the EXIT trap above always gets to run down()
  # SIGUSR1 = "restart everything", sent by Eden local's restart button. It only sets a flag; the loop below
  # does the work, so a request that arrives while Eden is still starting is not lost, and a second one during
  # a restart is ignored.
  trap '[[ $RESTARTING == 1 ]] || RESTART_REQUESTED=1' USR1
  up || { echo "start failed" >&2; return 1; }
  echo "Eden is running. Close this terminal (or press Ctrl+C) to shut everything down."
  while :; do
    if [[ $RESTART_REQUESTED == 1 ]]; then
      RESTART_REQUESTED=0
      RESTARTING=1
      echo "== restarting Eden =="
      down
      up || { echo "restart failed" >&2; return 1; }
      RESTARTING=0
      echo "Eden restarted."
    fi
    # Holds the terminal while any managed process (every one is a background job of this shell) is alive;
    # when none is left there is nothing to hold it for. A 1 s poll instead of "wait" so that no signal can slip
    # in between the flag check and the wait.
    [[ -n "$(jobs -p)" ]] || break
    sleep 1
  done
}

case "${1:-}" in
  "") foreground_all ;;
  up) up ;;
  down) down ;;
  vpn-up) vpn_up ;;
  vpn-down) vpn_down ;;
  vpn-reload) vpn_reload ;;
  remote-restart) remote_restart ;;
  local-up) local_up ;;
  local-down) local_down ;;
  status) status ;;
  *) echo "usage: $0 [up|down|vpn-up|vpn-down|vpn-reload|remote-restart|local-up|local-down|status]"
     echo "       $0 (no argument)  - foreground: start everything, tear it all down when this terminal closes"
     exit 2 ;;
esac
