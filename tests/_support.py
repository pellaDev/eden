# Shared setup of the Linux-edition tests: a scratch directory, the EDEN_* variables the backend reads, and the import
# paths. Tests need the packages of requirements.txt (fastapi, pydantic). Run one with `python3 tests/test_backend.py`
# or all with `python3 tests/run_all.py`. Nothing here touches the real configuration.
import importlib.util
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
T = tempfile.mkdtemp(prefix="eden-tests-")
for sub in ("eden-home/data/run", "eden-home/config"):
    os.makedirs(os.path.join(T, sub), exist_ok=True)
os.environ.update(EDEN_HOME=T + "/home", EDEN_CONFIG=T + "/eden-home/config/eden.json", MESH_IFACE="nordlynx", EDEN_LOGS=T,
                  EDEN_SECRETS=T, EDEN_RUN=T + "/eden-home/data/run", EDEN_HELPER="/bin/true", EDEN_AVATARS=T + "/av.json")
for sub in ("backend", os.path.join("bin", "eden_ctl"), os.path.join("bin", "eden_notify"), "core"):
    sys.path.insert(0, os.path.join(ROOT, sub))


def load(name, *relpath):
    """Import a script of the tree by path (the scripts in bin/ are not packages)."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, *relpath))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
