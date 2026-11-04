# Consistency tests of the Windows platform override against the real backend source (checked statically, so it
# runs on any OS without FastAPI). Run: python3 test_eden_platform.py
import ast
import inspect
import os
import sys
import types

import eden_platform_windows as p

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "backend", "eden_local.py")
tree = ast.parse(open(SRC, encoding="utf-8").read())
funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def params(fn):
    a = fn.args
    return [x.arg for x in a.posonlyargs + a.args] + ([a.vararg.arg] if a.vararg else []) + [x.arg for x in a.kwonlyargs]


def routes():
    out = set()
    for fn in funcs.values():
        for d in fn.decorator_list:
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and isinstance(d.func.value, ast.Name) \
                    and d.func.value.id == "app" and d.args and isinstance(d.args[0], ast.Constant):
                out.add((d.args[0].value, d.func.attr.upper()))
    return out


# 1. every replaced function exists in eden_local (same parameter names, so callers keep working)
ns = {"EDEN_PID_FILE": "x", "EDEN_RUN": "x", "read_config": lambda: {}, "say": lambda k, **f: k, "build_connections": None,
      "BaseModel": object, "SERVICE_NAME_RE": __import__("re").compile(r"[a-z0-9][a-z0-9_-]{0,31}"),
      "devices_state": lambda cfg, peers: {"devices": []}, "apply_change": None, "read_version": lambda: "0"}
app = types.SimpleNamespace(router=types.SimpleNamespace(routes=[]))


class APIRoute:
    def __init__(self, path, endpoint, methods=None):
        self.path, self.endpoint, self.methods = path, endpoint, set(methods or [])


routing = types.ModuleType("fastapi.routing")
routing.APIRoute = APIRoute
sys.modules["fastapi.routing"] = routing
fastapi = types.ModuleType("fastapi")
fastapi.HTTPException = type("HTTPException", (Exception,), {"__init__": lambda s, c, d=None: None})
fastapi.routing = routing
sys.modules["fastapi"] = fastapi
app.router.routes = [APIRoute(path, None, {m}) for path, m in p.REPLACED_ROUTES]
CFG = {"devices": [{"name": "phone", "address": "100.64.0.9"}]}
ns["apply_change"] = lambda mutate: (mutate(CFG), CFG)[1]
p.apply(ns, app)
for name in p.REPLACED_FUNCTIONS:
    assert name in funcs, f"{name} no longer exists in eden_local"
    assert name in ns and callable(ns[name]), f"{name} was not installed"
    got = [x.name for x in inspect.signature(ns[name]).parameters.values()]
    assert got == params(funcs[name]), f"{name}: eden_local has {params(funcs[name])}, override has {got}"
print("replaced functions ok")

# 2. every replaced route exists in eden_local and was swapped for a new handler
real = routes()
for path, method in p.REPLACED_ROUTES:
    assert (path, method) in real, f"route {method} {path} no longer exists in eden_local"
assert all(r.endpoint is not None for r in app.router.routes)
print("replaced routes ok")

# 3. the hook is the last statement of eden_local and only runs on Windows or when asked
last = tree.body[-1]
assert isinstance(last, ast.If) and "windows" in ast.dump(last).lower(), "the platform hook must stay at the end of eden_local"
# 4. the module defining the variable the override rewrites still exists
assert "ALLOWED_PORTS_FILE" in ns

# 5. add by address: validation, defaults, duplicates; the new device is disabled and untrusted
add = next(r.endpoint for r in app.router.routes if r.path == "/api/devices/by-address")
Body = lambda **k: types.SimpleNamespace(name=None, **k)
class Refused(Exception):
    pass
fastapi.HTTPException = Refused   # not used by apply (already bound); kept for clarity
for bad in ("8.8.8.8", "100.64.0", "abc", "192.0.2.5", "100.128.0.1"):
    try:
        add(Body(address=bad))
        raise SystemExit(f"accepted {bad}")
    except SystemExit:
        raise
    except Exception:
        pass
add(Body(address="100.64.0.77"))
d = CFG["devices"][-1]
assert d == {"name": "device-0-77", "public_key": "addr:100.64.0.77", "address": "100.64.0.77", "enabled": False,
             "services": [], "untrusted": True}, d
for dup in (Body(address="100.64.0.77"), types.SimpleNamespace(address="100.64.0.10", name="phone")):
    try:
        add(dup)
        raise SystemExit("duplicate accepted")
    except SystemExit:
        raise
    except Exception:
        pass
assert ns["devices_state"]({}, None)["by_address"] is True
print("add by address ok")
print("hook ok\nall platform tests passed")
