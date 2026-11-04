# Runs every test file of the Linux edition, each in its own process, and prints one line per file.
# Run: python3 tests/run_all.py   (needs the packages of requirements.txt)
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
