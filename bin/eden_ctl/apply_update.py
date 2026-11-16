#!/usr/bin/env python3
# Applies a staged self-update (see backend/eden_update.py). start.sh calls it before `up`, as:
#     apply_update.py <marker-json> <eden-home>
#
# The staged tree is overlaid onto the Eden home with plain copies, and nothing is ever deleted:
# files removed upstream simply stay on disk. Protected names are never touched, at any depth:
# data/, config/, secrets/, env/, .venv/, .git/, .gate-tmp/ and vars.env. Symlinks in the staged
# tree are skipped, not followed. On success the marker is removed. If the staging is invalid it is
# discarded with the marker (Eden keeps running as-is); if a copy fails, the marker and the staging
# are kept so the next restart retries.

import json
import os
import shutil
import sys

PROTECTED_DIRS = {"data", "config", "secrets", "env", ".venv", ".git", ".gate-tmp"}
PROTECTED_FILES = {"vars.env"}


def main():
    if len(sys.argv) != 3:
        print("usage: apply_update.py <marker> <eden-home>", file=sys.stderr)
        return 2
    marker_path = os.path.abspath(sys.argv[1])
    home = os.path.abspath(sys.argv[2])
    try:
        with open(marker_path, encoding="utf-8") as f:
            marker = json.load(f)
    except (OSError, ValueError):
        print("apply_update: cannot read the update marker", file=sys.stderr)
        return 1
    staging = os.path.abspath(str(marker.get("stagingDir") or ""))
    tag = str(marker.get("tag") or "?")

    run_dir = os.path.dirname(marker_path)
    if not staging.startswith(run_dir + os.sep):
        print(f"apply_update: staged directory outside the run directory ({tag}); discarding marker", file=sys.stderr)
        _clear_marker(marker_path)
        return 0
    if not os.path.isfile(os.path.join(staging, "VERSION")) or not os.path.isfile(os.path.join(staging, "start.sh")):
        print(f"apply_update: invalid staged update for {tag}; discarding", file=sys.stderr)
        shutil.rmtree(staging, ignore_errors=True)
        _clear_marker(marker_path)
        return 0

    copied = 0
    try:
        for dirpath, dirnames, filenames in os.walk(staging):
            rel_dir = os.path.relpath(dirpath, staging)
            parts = [] if rel_dir == "." else rel_dir.split(os.sep)
            if any(p in PROTECTED_DIRS or p in PROTECTED_FILES for p in parts):
                dirnames[:] = []          # never descend into a protected name
                continue
            target_dir = home if rel_dir == "." else os.path.join(home, rel_dir)
            os.makedirs(target_dir, exist_ok=True)
            for fn in filenames:
                src = os.path.join(dirpath, fn)
                if os.path.islink(src):
                    print(f"apply_update: skipping symlink {fn}", file=sys.stderr)
                    continue
                shutil.copy2(src, os.path.join(target_dir, fn))
                copied += 1
    except OSError as e:
        print(f"apply_update: copy failed ({e}); marker and staging kept for the next restart", file=sys.stderr)
        return 1

    _clear_marker(marker_path)
    print(f"apply_update: applied {tag} ({copied} files)")
    return 0


def _clear_marker(marker_path):
    try:
        os.remove(marker_path)
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
