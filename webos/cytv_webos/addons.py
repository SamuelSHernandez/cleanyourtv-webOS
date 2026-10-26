"""Add-ons: separate webOS apps that can show a module card on Home (docs/specs/card.md).

An add-on lives in addons/<name>/:

    app/            the webOS web app (appinfo.json, index.html, js/, css/): its own id, never the launcher's
    card.json       optional: {"spec": 1, "label": ..., "caption": ..., "accent": "#RRGGBB"}
    README.md       what it does, with a Permissions section (every permission and why; network use if any)
    screenshot.jpg  the add-on on a real TV (required in this repo, never packed)

Trust: the Android launcher binds a card to the app's signing key and asks on the TV. A webOS launcher can read
neither another app's files nor its signer, so the owner decides on the computer (`addon approve`), where the
card, the app id and the package's SHA-256 are shown; only approved cards are baked into the launcher. The
decision record holds the card exactly as approved: a changed label, caption or accent needs a new decision.
"""
import hashlib
import json
from pathlib import Path
import re
import time

from .errors import Refused
from . import ipk, store

ROOT = Path(__file__).resolve().parents[1]
ADDONS = ROOT / "addons"
TEXT_RE = re.compile(r"[A-Za-z0-9.&+' -]+")
RESERVED = {"home", "settings", "inputs", "wifi", "livetv", "applibrary", "choosedefaulthome", "clock",
            "defaulthome", "cleanyourtv", "tvvibehack", "launchersettings"}
MAX_DECISIONS = 128
VERSION = 1


def fold(text):
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def _text_ok(v, lo, hi):
    return (isinstance(v, str) and lo <= len(v) <= hi and v == v.strip(" ") and TEXT_RE.fullmatch(v) is not None
            and re.search(r"[A-Za-z0-9]", v) is not None and not re.search("verified|official", fold(v)))


def validate_card(card, app_id):
    """Upstream spec 1 rules (the same as launcher/js/cards.js). Returns the card or raises Refused."""
    if not isinstance(card, dict) or card.get("spec") != 1:
        raise Refused("card.json: spec must be 1")
    extra = set(card) - {"spec", "label", "caption", "accent"}
    if extra:
        raise Refused(f"card.json: unknown fields {sorted(extra)}")
    label = card.get("label")
    if not _text_ok(label, 1, 24):
        raise Refused("card.json: label must be 1-24 characters from A-Z a-z 0-9 space . & + ' - , with a letter or digit")
    f = fold(label)
    if f in RESERVED or f.startswith("hdmi") or f == "av":
        raise Refused(f"card.json: {label!r} is a name the launcher itself uses")
    caption = card.get("caption", "")
    if not isinstance(caption, str) or (caption and not _text_ok(caption, 1, 32)):
        raise Refused("card.json: caption must be up to 32 characters from the same set")
    if "accent" in card and not (isinstance(card["accent"], str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", card["accent"])):
        raise Refused("card.json: accent must be #RRGGBB")
    accent = card.get("accent")
    if accent is not None and not (isinstance(accent, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", accent)):
        raise Refused("card.json: accent must be #RRGGBB")
    return {"spec": 1, "app": app_id, "label": label, "caption": caption, **({"accent": accent} if accent else {})}


def load(folder):
    """{name, folder, app_dir, appinfo, card or None}. Refused when the add-on breaks the repo's rules."""
    folder = Path(folder)
    app_dir = folder / "app"
    info = ipk.read_appinfo(app_dir)
    readme = folder / "README.md"
    if not readme.is_file() or "## Permissions" not in readme.read_text(encoding="utf-8"):
        raise Refused(f"{folder}: README.md with a '## Permissions' section is required")
    card = None
    if (folder / "card.json").is_file():
        try:
            raw = json.loads((folder / "card.json").read_text(encoding="utf-8"))
        except ValueError as e:
            raise Refused(f"{folder}/card.json: not JSON ({e})")
        card = validate_card(raw, info["id"])
    return {"name": folder.name, "folder": folder, "app_dir": app_dir, "appinfo": info, "card": card}


def resolve(name_or_path):
    p = Path(name_or_path)
    if p.is_dir():
        return p
    if re.fullmatch(r"[a-z0-9-]{1,40}", name_or_path) and (ADDONS / name_or_path).is_dir():
        return ADDONS / name_or_path
    raise Refused(f"no add-on {name_or_path!r}: pass a folder, or a name from addons/")


def build(folder, out_dir):
    """Build an add-on's IPK; it must not use the launcher's id. Returns (path, sha256, appinfo).
    Icons named in appinfo.json and missing from the folder are drawn at build time, as the launcher's are."""
    import shutil
    from . import build as launcher_build
    a = load(folder)
    if a["appinfo"]["id"] == launcher_build.launcher_info()["id"]:
        raise Refused(f"{folder}: an add-on cannot use the launcher's app id")
    staging = Path(out_dir) / "addons" / "stage" / a["appinfo"]["id"]
    if staging.exists():
        shutil.rmtree(staging)
    for rel, src in ipk.app_files(a["app_dir"]):
        dst = staging / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    for key, size in (("icon", 80), ("largeIcon", 130)):
        name = a["appinfo"].get(key)
        if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_-]+\.png", name) and not (staging / name).exists():
            (staging / name).write_bytes(launcher_build.icon(size))
    path, digest, info = ipk.build(staging, Path(out_dir) / "addons")
    launcher_build.verify(path, expect_id=info["id"], expect_version=info["version"])
    return path, digest, info


# ---- decisions --------------------------------------------------------------------------------------------------

def decisions_path(device):
    return store.device_dir(device) / "cards.json"


def decisions(device):
    data = store.load_json(decisions_path(device), "card decisions", VERSION)
    if data is None:
        return []
    items = data.get("decisions")
    if not isinstance(items, list):
        raise Refused(f"{decisions_path(device)}: card decisions are unreadable; left where it is")
    return items


def decide(device, card, decision, other_titles, package_sha256):
    """Record show/hide for a card. A label equal to another installed app's name is refused, as upstream."""
    if decision not in ("show", "hide"):
        raise ValueError(decision)
    if decision == "show":
        clash = [t for t in other_titles if fold(t) == fold(card["label"])]
        if clash:
            raise Refused(f"the card's label {card['label']!r} is the name of another app on this TV ({clash[0]}); "
                          "a card may not take another app's name")
    items = [d for d in decisions(device) if d.get("app") != card["app"]]
    items.append({**card, "decision": decision, "package_sha256": package_sha256, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    store.write_json(decisions_path(device), {"version": VERSION, "decisions": items[-MAX_DECISIONS:]})


def shown_cards(device):
    """The cards to bake, oldest decision first (the launcher keeps the oldest one when two share a label)."""
    out = []
    for d in decisions(device):
        if d.get("decision") != "show":
            continue
        try:
            card = validate_card({k: d[k] for k in ("spec", "label", "caption", "accent") if k in d}, d.get("app"))
        except Refused:
            continue
        if isinstance(d.get("app"), str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", d["app"]):
            out.append(card)
    return out


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
