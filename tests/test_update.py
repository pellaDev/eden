# Offline tests of the update feature: version comparison, rpm NEVRA parsing, release staging (with its
# zip-slip and symlink guards), and the update marker. No network access is needed.
# Run: python3 tests/test_update.py
import os
import tempfile
import zipfile

from _support import load

u = load("update", "backend", "eden_update.py")

TOP = "eden-release"
REQUIRED = {
    "VERSION": b"0.17\n",
    "start.sh": b"#!/usr/bin/env bash\necho start\n",
    "requirements.txt": b"",
}


def make_zip(path, entries):
    """entries: {arcname: (text-or-bytes, mode)} where mode is the unix file mode."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, (data, mode) in entries.items():
            zi = zipfile.ZipInfo(name)
            zi.external_attr = (mode << 16) | (0o170000 if mode == 0o120000 else 0)
            zf.writestr(zi, data)


def valid_entries():
    e = {TOP + "/": (b"", 0o755)}
    for name, data in REQUIRED.items():
        e[TOP + "/" + name] = (data, 0o755 if name == "start.sh" else 0o644)
    e[TOP + "/backend/__init__.py"] = (b"", 0o644)
    e[TOP + "/bin/eden_ctl/x.py"] = (b"", 0o644)
    e[TOP + "/core/y.py"] = (b"", 0o644)
    e[TOP + "/webui/dist/index.html"] = (b"<html></html>", 0o644)
    return e


# --- version comparison -------------------------------------------------------
assert u.compare_versions("1", "1") == 0
assert u.compare_versions("v0.16", "0.16") == 0
assert u.compare_versions("1.2", "1.10") == -1
assert u.compare_versions("0.17", "0.16") == 1
assert u.compare_versions("1", "1.0") == 0
assert u.compare_versions("1.0.1", "1.0") == 1
assert u.compare_versions("2.0", "1.9.9") == 1

# --- rpm NEVRA parsing --------------------------------------------------------
n = u.parse_rpm_nevra("nordvpn-6.0.2-1.x86_64")
assert n == {"epoch": 0, "version": "6.0.2", "release": "1"}, n
n = u.parse_rpm_nevra("nordvpn-1:6.0.2-1.x86_64")
assert n == {"epoch": 1, "version": "6.0.2", "release": "1"}, n
assert u.parse_rpm_nevra("package-is-nordvpn-6.0.2-1.x86_64") is None
assert u.parse_rpm_nevra("not installed") is None
assert u.parse_rpm_nevra("") is None

# --- nordvpn update decision ---------------------------------------------------
inst = {"epoch": 0, "version": "6.0.1", "release": "1"}
repo = {"epoch": 0, "version": "6.0.2"}
assert u.nordvpn_update_available(inst, repo) is True
assert u.nordvpn_update_available({"epoch": 0, "version": "6.0.2"}, repo) is False
# an epoch bump wins over any version number
assert u.nordvpn_update_available({"epoch": 0, "version": "99.0"}, {"epoch": 1, "version": "1.0"}) is True

# --- release staging ----------------------------------------------------------
T = tempfile.mkdtemp(prefix="eden-update-test-")


def staged_case(name):
    zip_path = os.path.join(T, name + ".zip")
    dest = os.path.join(T, name)
    make_zip(zip_path, valid_entries())
    u.stage_release(zip_path, dest)
    for f in ("VERSION", "start.sh", "requirements.txt"):
        assert os.path.isfile(os.path.join(dest, f)), (name, f)
    for d in ("backend", "bin", "core", os.path.join("webui", "dist")):
        assert os.path.isdir(os.path.join(dest, d)), (name, d)
    assert not os.path.exists(os.path.join(dest, TOP))  # wrapper stripped
    return dest


staged_case("good")

# zip-slip entry is rejected
bad = valid_entries()
bad[TOP + "/../../evil.txt"] = (b"pwn", 0o644)
make_zip(os.path.join(T, "slip.zip"), bad)
try:
    u.stage_release(os.path.join(T, "slip.zip"), os.path.join(T, "slip"))
    raise SystemExit("zip-slip entry was not rejected")
except u.UpdateError as e:
    assert "unsafe path" in str(e), e

# symlink entry is rejected
bad = valid_entries()
bad[TOP + "/backend/evil"] = (b"/etc/passwd", 0o120000)
make_zip(os.path.join(T, "sym.zip"), bad)
try:
    u.stage_release(os.path.join(T, "sym.zip"), os.path.join(T, "sym"))
    raise SystemExit("symlink entry was not rejected")
except u.UpdateError as e:
    assert "symlink" in str(e), e

# a release missing required files is rejected
bad = {k: v for k, v in valid_entries().items() if not k.startswith(TOP + "/core")}
make_zip(os.path.join(T, "missing.zip"), bad)
try:
    u.stage_release(os.path.join(T, "missing.zip"), os.path.join(T, "missing"))
    raise SystemExit("release without core/ was not rejected")
except u.UpdateError as e:
    assert "core" in str(e), e

# a release without the built webui is rejected
bad = {k: v for k, v in valid_entries().items() if not k.startswith(TOP + "/webui")}
make_zip(os.path.join(T, "noweb.zip"), bad)
try:
    u.stage_release(os.path.join(T, "noweb.zip"), os.path.join(T, "noweb"))
    raise SystemExit("release without webui/dist was not rejected")
except u.UpdateError as e:
    assert "webui" in str(e), e

# --- nord repo metadata parsing (offline, canned responses) -----------------------
import gzip as _gzip

REPOMD = b'''<?xml version="1.0"?>
<repomd xmlns="http://linux.duke.edu/metadata/repo">
  <data type="primary">
    <location href="repodata/abc-primary.xml.gz"/>
  </data>
</repomd>'''
PRIMARY = b'''<?xml version="1.0"?>
<metadata xmlns="http://linux.duke.edu/metadata/common">
<package type="rpm">
  <name>nordvpn</name>
  <arch>x86_64</arch>
  <version epoch="0" ver="6.0.2" rel="1"/>
</package>
<package type="rpm">
  <name>nordvpn</name>
  <arch>i686</arch>
  <version epoch="0" ver="5.9.0" rel="1"/>
</package>
</metadata>'''


class FakeHttp:
    def __call__(self, url, timeout=15):
        if url.endswith("repomd.xml"):
            return REPOMD
        if url.endswith(".xml.gz"):
            return _gzip.compress(PRIMARY)
        raise AssertionError(url)


real_http = u.http_get
u.http_get = FakeHttp()
try:
    meta = u._repo_metadata()
finally:
    u.http_get = real_http
assert meta == {"epoch": 0, "version": "6.0.2"}, meta

# --- marker round-trip ----------------------------------------------------------
run_dir = os.path.join(T, "run")
os.makedirs(run_dir)
staging = staged_case("good")
u.write_marker(run_dir, "v0.17", staging)
m = u.read_marker(run_dir)
assert m is not None and m["tag"] == "v0.17" and m["stagingDir"] == staging, m
u.clear_marker(run_dir)
assert u.read_marker(run_dir) is None

# a corrupt marker is reported as absent, never raised
with open(os.path.join(run_dir, "update_request.json"), "w") as f:
    f.write("[not a marker]")
assert u.read_marker(run_dir) is None

print("ok test_update.py")
