"""Build the launcher's .ipk from launcher/ with the standard library only.

An .ipk is an `ar` archive of three members, in this order: `debian-binary` ("2.0\\n"),
`control.tar.gz` and `data.tar.gz`. The data tree holds the app under
`usr/palm/applications/<id>/` and a `packageinfo.json` under `usr/palm/packages/<id>/`, which is
the layout `ares-package` writes for a web app.

The build is repeatable: entries are sorted, owners are 0:0, every timestamp is SOURCE_DATE_EPOCH
(default 0) and gzip headers carry no name or time. Two builds of the same tree give the same bytes
on the same Python; that is a repeatable process, not a proof of byte-for-byte reproducibility
across toolchains.
"""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tarfile

from .errors import Refused

APP_ID_RE = re.compile(r"[a-z0-9]+(\.[a-z0-9]+){2,}")
VERSION_RE = re.compile(r"\d{1,5}\.\d{1,5}\.\d{1,5}")
# What may ship inside the package. Anything else under launcher/ (a stray editor file, a preview
# adapter) is refused rather than packed, so the IPK holds only the files the launcher loads.
ALLOWED_SUFFIXES = {".html", ".js", ".css", ".json", ".png", ".jpg", ".txt", ".woff2"}
# The preview adapter fabricates an app inventory; it must never reach a TV.
EXCLUDED_NAMES = {"preview-adapter.js", "preview.html"}


def _epoch():
    value = os.environ.get("SOURCE_DATE_EPOCH", "0")
    if not value.isdigit():
        raise Refused(f"SOURCE_DATE_EPOCH must be a whole number of seconds, not {value!r}")
    return int(value)


def read_appinfo(app_dir):
    path = Path(app_dir) / "appinfo.json"
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Refused(f"cannot read {path}: {e}")
    if not isinstance(info, dict):
        raise Refused(f"{path}: not a JSON object")
    app_id, version = info.get("id"), info.get("version")
    if not isinstance(app_id, str) or not APP_ID_RE.fullmatch(app_id):
        raise Refused(f"{path}: id must look like com.example.app, got {app_id!r}")
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise Refused(f"{path}: version must be MAJOR.MINOR.PATCH, got {version!r}")
    if info.get("type") != "web" or info.get("main") != "index.html":
        raise Refused(f"{path}: expected a web app whose main is index.html")
    return info


def app_files(app_dir):
    """The files that ship, as sorted (relative posix path, absolute path) pairs."""
    root = Path(app_dir)
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise Refused(f"{rel}: symbolic links are not packed")
        if path.name in EXCLUDED_NAMES or path.name.startswith("."):
            continue
        if path.suffix not in ALLOWED_SUFFIXES:
            raise Refused(f"{rel}: {path.suffix or 'no suffix'} is not a file type the launcher ships")
        files.append((rel, path))
    return files


def _tar_gz(entries, epoch):
    """entries: (name, bytes or None for a directory) in the order given."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.mtime = epoch
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            if data is None:
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tar.addfile(info)
            else:
                info.size = len(data)
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0, compresslevel=9) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def _dirs_for(paths):
    seen = []
    for path in paths:
        parts = path.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            d = "/".join(parts[:i]) + "/"
            if d not in seen:
                seen.append(d)
    return seen


def _ar(members, epoch):
    out = io.BytesIO()
    out.write(b"!<arch>\n")
    for name, data in members:
        header = (f"{name + '/':<16}{epoch:<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n").encode()
        if len(header) != 60:
            raise ValueError("ar header overflow")
        out.write(header)
        out.write(data)
        if len(data) % 2:
            out.write(b"\n")
    return out.getvalue()


def build(app_dir, out_dir):
    """Write <id>_<version>_all.ipk into out_dir and return (path, sha256, appinfo)."""
    info = read_appinfo(app_dir)
    app_id, version = info["id"], info["version"]
    epoch = _epoch()
    files = app_files(app_dir)
    if not any(rel == "index.html" for rel, _ in files):
        raise Refused("index.html is missing")
    app_prefix = f"usr/palm/applications/{app_id}/"
    pkg_prefix = f"usr/palm/packages/{app_id}/"
    payload = [(app_prefix + rel, path.read_bytes()) for rel, path in files]
    packageinfo = {
        "app": app_id,
        "id": app_id,
        "loc_name": info.get("title", app_id),
        "package_format_version": 2,
        "vendor": info.get("vendor", ""),
        "version": version,
    }
    payload.append((pkg_prefix + "packageinfo.json",
                    (json.dumps(packageinfo, indent=2, sort_keys=True) + "\n").encode()))
    payload.sort()
    names = [name for name, _ in payload]
    data_entries = [("./" + d, None) for d in _dirs_for(names)] + [("./" + n, b) for n, b in payload]
    installed_kb = max(1, sum(len(b) for _, b in payload) // 1024)
    control = (
        f"Package: {app_id}\n"
        f"Version: {version}\n"
        "Section: misc\n"
        "Priority: optional\n"
        "Architecture: all\n"
        f"Installed-Size: {installed_kb}\n"
        f"Maintainer: {info.get('vendor', 'unknown')}\n"
        f"Description: {info.get('title', app_id)}\n"
        "webOS-Package-Format-Version: 2\n"
        "webOS-Packager-Version: cytv-webos-ipk/1\n"
    ).encode()
    ipk = _ar([
        ("debian-binary", b"2.0\n"),
        ("control.tar.gz", _tar_gz([("./", None), ("./control", control)], epoch)),
        ("data.tar.gz", _tar_gz(data_entries, epoch)),
    ], epoch)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{app_id}_{version}_all.ipk"
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(ipk)
    os.replace(tmp, target)
    return target, hashlib.sha256(ipk).hexdigest(), info


def read_members(ipk_bytes):
    """Parse an ar archive into [(name, bytes)]; used by tests and `verify-ipk`."""
    if not ipk_bytes.startswith(b"!<arch>\n"):
        raise Refused("not an ar archive")
    pos, members = 8, []
    while pos < len(ipk_bytes):
        header = ipk_bytes[pos:pos + 60]
        if len(header) < 60 or header[58:60] != b"`\n":
            raise Refused("truncated ar header")
        name = header[:16].decode().strip().rstrip("/")
        size = int(header[48:58].decode().strip())
        pos += 60
        members.append((name, ipk_bytes[pos:pos + size]))
        pos += size + (size % 2)
    return members
