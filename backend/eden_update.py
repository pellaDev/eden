#!/usr/bin/env python3
# Update checks and staging for the self-update (Eden) and for NordVPN updates. Standard library only:
# the update feature adds no dependency.
#
# Self-update: the latest GitHub release of the public repo is fetched, its source zipball is downloaded
# and extracted with path-traversal and symlink guards into a staging directory under $EDEN_RUN, validated,
# and a marker file is written. start.sh applies the staged tree on the next `up` (an overlay copy over
# the Eden home - data/, config/, secrets/ and the virtualenv are never touched) and restarts.
#
# NordVPN: the installed package version (rpm, no root needed) is compared against the newest version
# published in Nord's official yum repository metadata (plain HTTP). The actual upgrade runs through the
# root helper (`nordvpn-upgrade`); this module only decides "is an update available".

import gzip
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

GITHUB_LATEST_URL = "https://api.github.com/repos/pellaDev/eden/releases/latest"
NORD_REPO_BASE = "https://repo.nordvpn.com/yum/nordvpn/centos/x86_64"
USER_AGENT = "Eden-local-update-check"
# Files the release must contain for a staged update to be accepted (checked after extraction).
REQUIRED_TOP_LEVEL = ("VERSION", "start.sh", "backend", "bin", "core", "requirements.txt")

_cache = {}


class UpdateError(Exception):
    """A readable update failure: its message is shown to the user as-is."""


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e:  # URLError, HTTPError, socket.timeout, ...
        raise UpdateError(f"cannot reach {url}: {e}") from e


def _version_key(s):
    """A sortable numeric key for a dotted version: 'v' prefix and non-numeric tails ignored."""
    parts = []
    for seg in str(s).strip().lstrip("vV").split("."):
        m = re.match(r"(\d+)", seg)
        parts.append(int(m.group(1)) if m else 0)
    # Fixed width, so that "1" and "1.0" compare equal instead of one key being a prefix of the other.
    return tuple(parts[:16] + [0] * (16 - min(len(parts), 16)))


def compare_versions(a, b):
    """Dotted-numeric comparison of two versions: -1, 0 or 1. Missing segments count as 0."""
    ka, kb = _version_key(a), _version_key(b)
    return (ka > kb) - (ka < kb)


def latest_eden_release():
    """The latest published GitHub release: {'tag': 'vX', 'zipball': url}."""
    def fetch():
        data = json.loads(http_get(GITHUB_LATEST_URL, 15))
        tag = str(data.get("tag_name") or "").strip()
        zipball = str(data.get("zipball_url") or "").strip()
        if not tag or not zipball.startswith("https://"):
            raise UpdateError("GitHub did not return a valid release")
        return {"tag": tag, "zipball": zipball}
    return _cached("github", 60, fetch)


def _cached(name, ttl, fn):
    now = time.time()
    hit = _cache.get(name)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = fn()
    _cache[name] = (now, value)
    return value


def parse_rpm_nevra(text):
    """'nordvpn-6.0.2-1.x86_64' -> {'epoch', 'version', 'release'}; None if not a valid NEVRA."""
    m = re.fullmatch(r"nordvpn-(?:(\d+):)?([A-Za-z0-9.]+)-([A-Za-z0-9]+)\.[A-Za-z0-9_]+", text.strip())
    if not m:
        return None
    epoch, version, release = m.groups()
    return {"epoch": int(epoch or 0), "version": version, "release": release}


def installed_nordvpn_version():
    """The installed NordVPN package version via rpm (no root needed). None if not installed."""
    try:
        r = subprocess.run(["rpm", "-q", "nordvpn"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    out = (r.stdout or "").strip()
    first = out.splitlines()[0].strip() if out else ""
    nevra = parse_rpm_nevra(first)
    return nevra


def _repo_metadata():
    repomd = ET.fromstring(http_get(NORD_REPO_BASE + "/repodata/repomd.xml", 20))
    ns = {"r": repomd.tag.split("}")[0][1:]} if "}" in repomd.tag else {}
    href = None
    for data in repomd.findall("r:data", ns):
        if data.get("type") == "primary":
            loc_el = data.find("r:location", ns)
            if loc_el is not None and loc_el.get("href"):
                href = loc_el.get("href").strip()
    if not href:
        raise UpdateError("the repository metadata has no primary file")
    raw = http_get(NORD_REPO_BASE + "/" + href.lstrip("/"), 30)
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    root = ET.fromstring(raw)
    ns2 = {"r": root.tag.split("}")[0][1:]} if "}" in root.tag else {}
    best_key, best_version = None, None
    for pkg in root.findall("r:package", ns2):
        if pkg.findtext("r:name", "", ns2) != "nordvpn":
            continue
        ver_el = pkg.find("r:version", ns2)
        if ver_el is None:
            continue
        epoch = int(ver_el.get("epoch") or 0)
        version = ver_el.get("ver") or ""
        key = (epoch, _version_key(version))
        if best_key is None or key > best_key:
            best_key, best_version = key, version
    if best_version is None:
        raise UpdateError("no nordvpn package in the repository metadata")
    return {"epoch": best_key[0], "version": best_version}


def nordvpn_repo_latest():
    """The newest published version of the 'nordvpn' package in Nord's yum repo (HTTP only)."""
    return _cached("nordrepo", 120, _repo_metadata)


def nordvpn_update_available(installed, repo):
    """installed/repo are dicts from installed_nordvpn_version()/nordvpn_repo_latest()."""
    return ((repo["epoch"], _version_key(repo["version"]))) > ((installed["epoch"], _version_key(installed["version"])))


def stage_release(zip_path, dest_dir):
    """Extract a release zipball into dest_dir with guards. Returns the extracted tree root."""
    if os.path.exists(dest_dir):
        shutil.rmtree(dest_dir)
    os.makedirs(dest_dir)
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as e:
        raise UpdateError("the downloaded file is not a valid zip archive") from e
    with zf:
        infos = zf.infolist()
        tops = set()
        for i in infos:
            name = i.filename
            if name.startswith("/") or ".." in name.split("/"):
                raise UpdateError(f"unsafe path in the archive: {name}")
            if not name or name.endswith("/"):
                continue
            tops.add(name.split("/", 1)[0])
        if len(tops) != 1:
            raise UpdateError("the archive does not contain a single top-level folder")
        top = tops.pop()
        for i in infos:
            name = i.filename
            mode = (i.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise UpdateError(f"the archive contains a symlink: {name}")
            rel = name[len(top) + 1:] if name.startswith(top + "/") else None
            if rel is None or rel == "":
                continue
            target = os.path.join(dest_dir, rel)
            if not os.path.realpath(target).startswith(os.path.realpath(dest_dir) + os.sep):
                raise UpdateError(f"unsafe path in the archive: {name}")
            if name.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(i) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            perm = (i.external_attr >> 16) & 0o7777
            if perm:
                os.chmod(target, perm)
    _validate_staged(dest_dir)
    return dest_dir


def _validate_staged(root):
    missing = [n for n in REQUIRED_TOP_LEVEL if not os.path.exists(os.path.join(root, n))]
    if missing:
        raise UpdateError("the release is missing required files: " + ", ".join(missing))
    if not os.path.isdir(os.path.join(root, "webui", "dist")):
        raise UpdateError("the release has no built webui (webui/dist)")


def write_marker(run_dir, tag, staging_dir):
    """Atomically write the update marker that start.sh will apply on the next up."""
    marker = os.path.join(run_dir, "update_request.json")
    tmp = marker + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"tag": tag, "stagingDir": staging_dir, "requestedAt": int(time.time())}, f)
    os.replace(tmp, marker)
    return marker


def read_marker(run_dir):
    """The pending update request, or None."""
    try:
        with open(os.path.join(run_dir, "update_request.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("tag"), str) or not isinstance(data.get("stagingDir"), str):
        return None
    return data


def clear_marker(run_dir):
    try:
        os.remove(os.path.join(run_dir, "update_request.json"))
    except OSError:
        pass
