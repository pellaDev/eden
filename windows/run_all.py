# Runs every test file of the Windows edition, each in its own process, one line per file. These tests use fakes for
# the platform (a fake firewall, an injectable icacls, the local transport of this machine), so they run on any
# system; the real Windows behaviour is only checked on a real Windows machine. They cannot check the guard state and
# the task on Windows itself - see docs/windows.md.
# Run: python windows\run_all.py   (needs the packages of windows/requirements-windows.txt)
import glob
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
failed = []
for path in sorted(glob.glob(os.path.join(here, "test_*.py"))):
    r = subprocess.run([sys.executable, path], capture_output=True, text=True, cwd=here)
    print(("ok   " if r.returncode == 0 else "FAIL ") + os.path.basename(path))
    if r.returncode:
        failed.append(path)
        print((r.stdout + r.stderr)[-1500:])
sys.exit(1 if failed else 0)
