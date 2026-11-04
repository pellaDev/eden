# Eden, Windows edition: how the normal-user processes ask the elevated helper (eden_winhelper.py) for something.
# One request per connection over the named pipe; the shared secret is read from %ProgramData%\Eden\helper.key.
# Standard library only; nothing of it is imported by the Linux edition.

import os
import subprocess
import sys
import time
from multiprocessing import connection

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import eden_winhelper as hp  # noqa: E402

TASK_NAME = "Eden helper"     # the scheduled task the install script creates (highest privileges, run on demand)
START_PAUSE = 30.0            # seconds: do not ask the task scheduler again sooner than this (no task = nothing to wait for)
_last_start = [0.0]


def start_task():
    """Ask the task scheduler to start the helper. True when the task exists and was started."""
    try:
        r = subprocess.run(["schtasks.exe", "/run", "/tn", TASK_NAME], capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def call(cmd, address=hp.PIPE, family=None, key=None, env=None, starter=None, wait=8.0, **params):
    """Send one command; returns the helper's answer dict. When nothing listens yet, the helper is started on demand
    through its scheduled task (`starter`, by default only on Windows) and the call waits up to `wait` seconds.
    Raises SystemExit with a clear text when the helper still cannot be reached: "not running" is a reportable state."""
    family = family or ("AF_PIPE" if os.name == "nt" else "AF_UNIX")
    if starter is None and os.name == "nt":
        starter = start_task
    deadline, started = None, False
    while True:
        try:
            key = key or hp.read_key(env)
            with connection.Client(address, family, authkey=key) as conn:
                conn.send({"cmd": cmd, **params})
                return conn.recv()
        except (OSError, EOFError, connection.AuthenticationError, hp.HelperError) as e:
            # Only "nobody is listening" is worth a start: a wrong key or a missing key file will not fix itself.
            waiting = isinstance(e, (OSError, EOFError)) and not isinstance(e, connection.AuthenticationError)
            if waiting and starter and not started and time.monotonic() - _last_start[0] > START_PAUSE:
                _last_start[0] = time.monotonic()
                started = bool(starter())
                deadline = time.monotonic() + wait if started else None
            if waiting and deadline and time.monotonic() < deadline:
                time.sleep(0.3)
                continue
            sys.exit(f"eden: the Windows helper is not reachable ({e}). Start it with the 'Eden helper' scheduled task.")
