# Eden, Linux edition: the ONE place that talks to the nordvpn command and reads its text output. Nord has no stable
# machine-readable interface, so everything that depends on its wording lives here, and a change of that wording is
# reported as such ("Nord's output is not what Eden expects") instead of showing up as missing devices or a vague
# refusal somewhere else. Standard library only.
#
# What Eden reads:
#   nordvpn settings               "Key: value" lines (Routing, Kill Switch, Auto-connect, ...)
#   nordvpn meshnet peer list      sections "This device:", "Local Peers:", "External Peers:", blocks of "Key: value"
# What Eden writes goes through the CLI too (set ..., meshnet peer ... allow/deny); only its exit status is used.
# The text matching that remains outside this file is the "already enabled" answer of `nordvpn set meshnet on` in
# start.sh, which only makes that step idempotent.

import os
import shlex
import subprocess

# Key added to a parsed peer that Nord lists under "External Peers". Not a Nord field name (no collision possible).
EXTERNAL = "__external__"
SECTIONS = {"This device:": "this", "Local Peers:": "local", "External Peers:": "external"}
# What every peer block must carry for Eden to use it: the key it is identified by, its address, a name to address it by.
PEER_REQUIRED = ("Public Key", "IP")


class NordFormatError(Exception):
    """The nordvpn output does not have the shape Eden was written for (a Nord update, most likely)."""


def nordvpn(*args):
    """Run the nordvpn CLI; returns (returncode, combined output). NORD_USE_SG=1 runs it under the "nordvpn" group."""
    if os.environ.get("NORD_USE_SG") == "1":
        argv = ["sg", "nordvpn", "-c", shlex.join(["nordvpn", *args])]
    else:
        argv = ["nordvpn", *args]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout + r.stderr


def parse_settings(text):
    """'Key: value' lines of 'nordvpn settings' -> {key: lowercase value}."""
    out = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            out[key.strip()] = value.strip().lower()
    return out


def parse_peer_list(text):
    """Parse 'nordvpn meshnet peer list' into (this_device, peers): local peers (own account) and external
    peers (other accounts). Every external peer carries EXTERNAL=True, so it can never be mistaken for a
    local one. Peer blocks are separated by a blank line and the key order inside a block is not guaranteed
    (a peer with no nickname prints Hostname before Nickname), so a block is closed by the blank line."""
    section, current, this, peers = None, None, {}, []
    for raw in text.splitlines():
        line = raw.strip()
        if line in SECTIONS:
            section = SECTIONS[line]
            current = this if section == "this" else None
        elif not line:
            if section in ("local", "external"):
                current = None
        elif ":" in line:                       # "[no peers]" has no colon: skipped
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip()
            if section == "this":
                this[key] = value
            elif section in ("local", "external"):
                if current is None:
                    current = {EXTERNAL: True} if section == "external" else {}
                    peers.append(current)
                current[key] = value
    return this, peers


def check_peer_list(text, this, peers):
    """Raise NordFormatError when the text parsed into something Eden cannot trust: no section heading at all, or a
    peer without its key, address or any name. An honest empty list ("[no peers]") is fine."""
    if text.strip() and not any(h in text for h in SECTIONS):
        raise NordFormatError("the peer list has none of the sections Eden knows ('This device:', 'Local Peers:', "
                              "'External Peers:'): this Nord version words it differently")
    for p in peers:
        missing = [k for k in PEER_REQUIRED if not p.get(k)]
        if not (p.get("Hostname") or p.get("Nickname")):
            missing.append("Hostname or Nickname")
        if missing:
            who = p.get("Hostname") or p.get("Nickname") or p.get("IP") or "a peer"
            raise NordFormatError(f"{who}: the peer list does not report {', '.join(missing)}: this Nord version words it differently")


def peer_target(peer):
    """Name the CLI can address this peer by. 'nordvpn meshnet peer ... <name>' accepts the
    Hostname or the Nickname, and neither is guaranteed to be present, so pick the first one."""
    return peer.get("Hostname") or peer.get("Nickname") or ""


def read_peers():
    """The live peers, checked. Raises NordFormatError on an unexpected format and RuntimeError when the command fails."""
    rc, out = nordvpn("meshnet", "peer", "list")
    if rc:
        raise RuntimeError(f"peer list failed: {out.strip()}")
    this, peers = parse_peer_list(out)
    check_peer_list(out, this, peers)
    return peers
