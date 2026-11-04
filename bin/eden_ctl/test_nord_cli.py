# Tests of the Nord CLI layer with sample outputs (documentation names and addresses only). Run: python3 test_nord_cli.py
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nord_cli as n

SAMPLE = """This device:
Nickname: workstation
Hostname: example-one.example
IP: 100.64.0.1
Public Key: KEYHOST
OS: linux

Local Peers:
Nickname: phone
Hostname: example-two.example
Status: disconnected
IP: 100.64.0.7
Public Key: KEYPHONE
OS: android
Allow Incoming Traffic: enabled
Allow Routing: disabled

Hostname: example-three.example
Nickname: -
Status: connected
IP: 100.64.0.8
Public Key: KEYTAB
OS: android


External Peers:
Hostname: friend-pc.example
Nickname: -
Status: connected
IP: 100.64.0.20
Public Key: KEYFRIEND
OS: windows
Allow Incoming Traffic: enabled
Allows Incoming Traffic: enabled
"""


def test_parse():
    this, peers = n.parse_peer_list(SAMPLE)
    assert this["Public Key"] == "KEYHOST" and len(peers) == 3
    assert [bool(p.get(n.EXTERNAL)) for p in peers] == [False, False, True]
    assert peers[1]["Hostname"] == "example-three.example" and peers[1]["Nickname"] == "-"   # Hostname-first block
    n.check_peer_list(SAMPLE, this, peers)


def test_no_peers_is_fine():
    text = "This device:\nHostname: a.example\nIP: 100.64.0.1\nPublic Key: K\n\nLocal Peers:\n[no peers]\n\nExternal Peers:\n[no peers]\n"
    this, peers = n.parse_peer_list(text)
    assert peers == []
    n.check_peer_list(text, this, peers)


def refused(text):
    this, peers = n.parse_peer_list(text)
    try:
        n.check_peer_list(text, this, peers)
    except n.NordFormatError as e:
        return str(e)
    return None


def test_changed_format_is_named():
    assert "sections" in refused("Peers:\n  - phone (100.64.0.7)\n")
    assert "Public Key" in refused(SAMPLE.replace("Public Key: KEYPHONE\n", ""))
    assert "IP" in refused(SAMPLE.replace("IP: 100.64.0.8\n", ""))
    assert "Hostname or Nickname" in refused("Local Peers:\nIP: 100.64.0.9\nPublic Key: K\n")
    assert refused("") is None


def test_settings():
    s = n.parse_settings("Routing: disabled\nKill Switch: Disabled\nAuto-connect: disabled\nNotify: enabled\n")
    assert s == {"Routing": "disabled", "Kill Switch": "disabled", "Auto-connect": "disabled", "Notify": "enabled"}


def test_cli_group_wrapper():
    calls = []
    real = n.subprocess.run
    n.subprocess.run = lambda argv, **k: calls.append(argv) or type("R", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()
    try:
        os.environ.pop("NORD_USE_SG", None)
        n.nordvpn("settings")
        os.environ["NORD_USE_SG"] = "1"
        n.nordvpn("meshnet", "peer", "list")
    finally:
        n.subprocess.run = real
        os.environ.pop("NORD_USE_SG", None)
    assert calls[0] == ["nordvpn", "settings"]
    assert calls[1] == ["sg", "nordvpn", "-c", "nordvpn meshnet peer list"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("NORD CLI TESTS PASSED")
