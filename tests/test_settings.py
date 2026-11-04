# Tests of 'eden_ctl settings' against a sample Nord 6.0.1 output. Run: python3 tests/test_settings.py
import contextlib
import io

from _support import load

c = load("ctl", "bin", "eden_ctl", "eden_ctl.py")
REAL601 = """Protocol: NordLynx
Firewall: enabled
Firewall Mark: 0xe1f1
Routing: disabled
User Consent: disabled
Kill Switch: disabled
Real-time protection: disabled
Notify: disabled
Tray: disabled
Auto-connect: disabled
Meshnet: disabled
DNS: disabled
LAN Discovery: disabled
Post-quantum VPN: disabled
ARP Ignore: enabled
"""
calls = []
def fake(*a): calls.append(a); return (0, REAL601) if a == ("settings",) else (0, "")
c.nordvpn = fake
with contextlib.redirect_stderr(io.StringIO()) as e, contextlib.redirect_stdout(io.StringIO()) as o: c.cmd_settings(None)
assert "settings ok" in o.getvalue() and "Virtual Location" in e.getvalue() and calls == [("settings",)], (o.getvalue(), e.getvalue(), calls)
# a present-but-enabled cosmetic setting is still switched off
calls.clear(); REAL = REAL601.replace("Tray: disabled", "Tray: enabled")
c.nordvpn = lambda *a: (calls.append(a) or (0, REAL if a == ("settings",) else ""))
with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()): c.cmd_settings(None)
assert ("set", "tray", "off") in calls
# a missing SAFETY setting still refuses
REAL = REAL601.replace("Kill Switch: disabled\n", "")
try:
    with contextlib.redirect_stderr(io.StringIO()): c.cmd_settings(None); raise SystemExit("NO REFUSAL")
except SystemExit as ex: assert "does not report Kill Switch" in str(ex.code), ex.code
print("settings tests ok")
