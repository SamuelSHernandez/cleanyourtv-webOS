"""The TV's app list and icons, read over SSAP and kept on the computer for the next build.

Approach from Razdva122/clean-your-tv-lg-webos@d5804f6 (cytv/tv.py, cytv/package.py) and
OmkarK97/webos-vibehack@31a518a (sync-apps.py); the host/port/size/type limits are this project's.

A Developer Mode web app cannot be assumed to list the TV's apps itself (the reference no-root
projects both bake the list in at install time), so the build bakes it in. The launcher still
probes the platform once at runtime and prefers a live answer when it gets one.

Icons are fetched only from the paired TV itself (same host, ports 3000/3001, no redirects),
at most MAX_ICON bytes each, and only kept when the bytes are a PNG or JPEG image. They are
stored under hashed names, so an app id never becomes a path.
"""
import hashlib
import http.client
import re
import json
import ssl
import time
from urllib.parse import urlsplit

from .errors import Refused, TransportError
from . import ssap, store

VERSION = 1
MAX_ICON = 256 * 1024
MAX_APPS = 300
COLOR_RE = re.compile(r"#[0-9A-Fa-f]{6}")
LABEL_RE = re.compile(r"[^\x00-\x1f\x7f]{1,32}")
ICON_PORTS = {3000, 3001}


def inv_dir(device):
    return store.device_dir(device) / "inventory"


def load(device):
    data = store.load_json(inv_dir(device) / "inventory.json", "app inventory", VERSION)
    if data is None:
        return None
    validate(data)
    return data


def validate(data):
    apps = data.get("apps")
    if not isinstance(apps, list) or len(apps) > MAX_APPS:
        raise Refused("inventory: apps must be a list of at most %d" % MAX_APPS)
    for a in apps:
        if not (isinstance(a, dict) and isinstance(a.get("id"), str) and ssap.APP_ID_RE.fullmatch(a["id"])
                and isinstance(a.get("title"), str) and 0 < len(a["title"]) <= 64
                and (a.get("art") is None or (isinstance(a["art"], str) and _art_name_ok(a["art"])))
                and (a.get("color") is None or (isinstance(a["color"], str) and COLOR_RE.fullmatch(a["color"])))):
            raise Refused(f"inventory: invalid app entry {str(a)[:80]}")
    inputs = data.get("inputs", [])
    if not isinstance(inputs, list) or len(inputs) > 16 or not all(
            isinstance(x, dict) and isinstance(x.get("app"), str) and ssap.APP_ID_RE.fullmatch(x["app"])
            and isinstance(x.get("label"), str) and 0 < len(x["label"]) <= 32 and LABEL_RE.fullmatch(x["label"])
            for x in inputs):
        raise Refused("inventory: invalid inputs")
    sc = data.get("shortcuts")
    if not isinstance(sc, dict) or not all(v is None or (isinstance(v, str) and ssap.APP_ID_RE.fullmatch(v))
                                           for v in sc.values()):
        raise Refused("inventory: invalid shortcuts")
    return data


def _art_name_ok(name):
    return len(name) == 20 and name[:16].isalnum() and name[16:] in (".png", ".jpg")


def image_kind(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    return None


def fetch_icon(url, host, pinned_sha256, timeout=10.0):
    """Icon bytes, or None when the URL is not one this tool will fetch or the answer is not an image."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or parts.hostname != host.strip("[]") or port not in ICON_PORTS:
        return None
    path = parts.path + (("?" + parts.query) if parts.query else "")
    try:
        if parts.scheme == "https":
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            conn = http.client.HTTPSConnection(parts.hostname, port, timeout=timeout, context=ctx)
            conn.connect()
            cert = conn.sock.getpeercert(binary_form=True) or b""
            if hashlib.sha256(cert).hexdigest() != pinned_sha256:
                conn.close()
                return None
        else:
            conn = http.client.HTTPConnection(parts.hostname, port, timeout=timeout)
        conn.request("GET", path or "/")
        resp = conn.getresponse()
        if resp.status != 200:
            conn.close()
            return None
        data = resp.read(MAX_ICON + 1)
        conn.close()
    except (OSError, http.client.HTTPException, ssl.SSLError):
        return None
    if len(data) > MAX_ICON or not image_kind(data):
        return None
    return data


def external_inputs(session):
    """The TV's inputs (HDMI, AV) as [{app, label}] for the Inputs menu; [] when the TV does not say."""
    try:
        answer = session.request("ssap://tv/getExternalInputList")
    except TransportError:
        return []
    out = []
    for d in answer.get("devices") or []:
        if not isinstance(d, dict):
            continue
        app, label = d.get("appId"), d.get("label") or d.get("id")
        if isinstance(app, str) and ssap.APP_ID_RE.fullmatch(app) and isinstance(label, str) and LABEL_RE.fullmatch(label.strip() or "-"):
            out.append({"app": app, "label": label.strip()[:32]})
    return out[:16]


def sync(device, host, session, profile, fetch=fetch_icon):
    """Read the TV's apps over SSAP, fetch icons, and write the inventory record."""
    creds = ssap.load_creds(device) or {}
    points = [p for p in ssap.launch_points(session) if not p["hidden"]]
    if len(points) > MAX_APPS:
        raise TransportError(f"the TV listed {len(points)} apps; this tool keeps at most {MAX_APPS}")
    every = ssap.all_apps(session)
    shortcuts = {k: next((a for a in ids if a in every), None)
                 for k, ids in profile["shortcut_candidates"].items()}
    inputs = external_inputs(session)
    folder = inv_dir(device)
    art_dir = folder / "art"
    art_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    apps, missing_art = [], 0
    for p in points:
        art = None
        data = fetch(p["icon"], host, creds.get("cert_sha256")) if p["icon"] else None
        if data:
            art = hashlib.sha256(p["id"].encode()).hexdigest()[:16] + image_kind(data)
            (art_dir / art).write_bytes(data)
        else:
            missing_art += 1
        apps.append({"id": p["id"], "title": p["title"], "art": art, "color": p.get("color")})
    record = {"version": VERSION, "synced": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "apps": apps, "inputs": inputs, "shortcuts": shortcuts}
    validate(record)
    store.write_json(folder / "inventory.json", record)
    return record, missing_art


def baked_script(record, launcher_id, generated_by, cards=None):
    """inventory.js for the package: data only, safe inside a classic script."""
    data = {"version": VERSION, "synced": record.get("synced") if record else None, "launcherId": launcher_id,
            "generatedBy": generated_by,
            "apps": [{"id": a["id"], "title": a["title"], "icon": ("art/" + a["art"]) if a["art"] else None,
                      "color": a.get("color")} for a in (record["apps"] if record else [])],
            "inputs": record.get("inputs", []) if record else [],
            "cards": cards or [],
            "shortcuts": record["shortcuts"] if record else {"inputs": None, "settings": None, "livetv": None}}
    text = json.dumps(data, ensure_ascii=True, sort_keys=True)
    text = text.replace("<", "\\u003c").replace(">", "\\u003e")
    return "/* Generated by cytv-webos build. Data only. */\nwindow.CYTV = window.CYTV || {};\nwindow.CYTV.baked = " + text + ";\n"
