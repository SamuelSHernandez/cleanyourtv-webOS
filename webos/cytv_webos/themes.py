"""Themes: a folder with config.json and optional pictures, validated and baked into the launcher package.

A theme folder holds what an upstream theme holds (Gathin23/cleanyourtv themes/README.md):

    config.json         keys from the schema in launcher/js/config.js, every one optional
    wallpaper.jpg       one picture (or wallpaper.png), or
    wallpapers/         a collection (*.jpg, *.png), with an optional captions.txt
    screenshot.jpg      Home with this theme on a real TV (required in this repo, never packed)
    CREDITS.md, *.md    attribution and notes (never packed)
    make_*.py           a script that drew the pictures (never packed)

The launcher ignores an unknown or wrongly typed key at runtime, as upstream's does; the build is stricter and
refuses a theme with any key it would ignore, so a typo is caught before it reaches a TV. Pictures are checked by
their bytes (PNG or JPEG), name and size; nothing in a theme can carry script, CSS or a URL.
"""
import hashlib
import json
from pathlib import Path
import re

from .errors import Refused
from . import inventory

ROOT = Path(__file__).resolve().parents[1]
CONFIG_JS = ROOT / "launcher" / "js" / "config.js"
THEMES = ROOT / "themes"
FILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\.(jpg|png)")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
MAX_PICTURE = 600 * 1024
MAX_TOTAL = 12 * 1024 * 1024
MAX_PICTURES = 48
RESERVED_KEYS = {8, 13, 27, 33, 34, 37, 38, 39, 40, 461, 447, 448, 449, 1056, 1057}
TARGETS = {"inputs", "settings", "livetv", "library"}
NOT_PACKED = re.compile(r"(screenshot\.jpg|[A-Za-z0-9_-]+\.md|make_[a-z0-9_]+\.py)")


def schema():
    """The launcher's key schema, read from between the markers in config.js."""
    text = CONFIG_JS.read_text(encoding="utf-8")
    m = re.search(r"/\* SCHEMA-BEGIN \*/(.*?)/\* SCHEMA-END \*/", text, re.S)
    if not m:
        raise Refused(f"{CONFIG_JS}: schema markers not found")
    return json.loads(m.group(1))


def _list(v, ok, limit=64):
    return isinstance(v, list) and len(v) <= limit and all(ok(x) for x in v)


def _js_len(s):
    """Length as JavaScript counts it (UTF-16 code units), so the build and the TV agree on limits."""
    return len(s.encode("utf-16-le")) // 2


def _ctrl(s):
    return re.search(r"[\x00-\x1f\x7f]", s) is not None


def check(spec, v):
    """The same rules as check() in launcher/js/config.js."""
    t = spec["type"]
    if t == "bool":
        return isinstance(v, bool)
    if t == "int":
        return isinstance(v, int) and not isinstance(v, bool) and spec["min"] <= v <= spec["max"]
    if t == "color":
        return isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v) is not None
    if t == "enum":
        return v in spec["values"]
    if t == "appId":
        return v == "" or (isinstance(v, str) and ID_RE.fullmatch(v) is not None)
    if t == "text":
        return isinstance(v, str) and _js_len(v) <= spec["max"] and not _ctrl(v)
    if t == "locale":
        return v == "" or (isinstance(v, str) and re.fullmatch(r"[A-Za-z]{2,3}([-_][A-Za-z0-9]{2,8}){0,2}", v) is not None)
    if t == "appIds":
        return _list(v, lambda x: isinstance(x, str) and ID_RE.fullmatch(x) is not None)
    if t == "appLabels":
        def label(x):
            m = isinstance(x, str) and re.fullmatch(r"([^=]+)=(.+)", x)
            return bool(m) and ID_RE.fullmatch(m.group(1)) is not None and _js_len(m.group(2)) <= 40 and not _ctrl(m.group(2))
        return _list(v, label)
    if t == "appKeys":
        def key(x):
            m = isinstance(x, str) and re.fullmatch(r"([0-9]{1,5}):(.+)", x)
            if not m:
                return False
            code = int(m.group(1))
            return 0 < code < 65536 and code not in RESERVED_KEYS and (m.group(2) in TARGETS or ID_RE.fullmatch(m.group(2)) is not None)
        return _list(v, key)
    if t == "moods":
        if v is None:
            return True
        return isinstance(v, dict) and set(v) <= {"morning", "evening", "night"} and all(
            _list(files, lambda f: isinstance(f, str) and FILE_RE.fullmatch(f) is not None) for files in v.values())
    return False


def _picture(path):
    data = path.read_bytes()
    if len(data) > MAX_PICTURE:
        raise Refused(f"{path}: {len(data) // 1024} KB; a theme picture is at most {MAX_PICTURE // 1024} KB")
    kind = inventory.image_kind(data)
    if kind is None or not path.name.endswith(kind[1:]):
        raise Refused(f"{path}: not a PNG or JPEG matching its name")
    return data


def load(folder):
    """A validated theme: {name, hash, config, wallpapers: {single, files, captions}, files: {packed path: bytes}}."""
    folder = Path(folder)
    if not (folder / "config.json").is_file():
        raise Refused(f"{folder}: no config.json")
    raw = (folder / "config.json").read_bytes()
    if len(raw) > 64 * 1024:
        raise Refused(f"{folder}/config.json: larger than 64 KB")
    try:
        config = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise Refused(f"{folder}/config.json: not JSON ({e})")
    if not isinstance(config, dict):
        raise Refused(f"{folder}/config.json: not an object")
    keys = schema()
    bad = [k for k in config if k not in keys or not check(keys[k], config[k])]
    if bad:
        raise Refused(f"{folder}/config.json: unknown or invalid keys: {', '.join(sorted(bad))} "
                      "(the keys are in themes/README.md)")
    files = {}
    single = None
    pictures = []
    captions = ""
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder).as_posix()
        # A link anywhere on the way (older Pythons follow linked folders in rglob) is refused before anything
        # is read, so nothing outside the theme folder can be packed.
        if any((folder / Path(*path.relative_to(folder).parts[:i + 1])).is_symlink()
               for i in range(len(path.relative_to(folder).parts))):
            raise Refused(f"{folder}/{rel}: symbolic links are not packed")
        if any(part.startswith(".") for part in path.relative_to(folder).parts):
            continue   # .DS_Store and other hidden files: never packed, as ipk.app_files
        if path.is_dir():
            if rel != "wallpapers":
                raise Refused(f"{folder}: unexpected folder {rel}")
            continue
        if rel == "config.json" or NOT_PACKED.fullmatch(rel):
            continue
        if rel in ("wallpaper.jpg", "wallpaper.png"):
            if single:
                raise Refused(f"{folder}: wallpaper.jpg and wallpaper.png both present; keep one")
            files["theme/" + rel] = _picture(path)
            single = rel
        elif rel == "wallpapers/captions.txt":
            captions = path.read_text(encoding="utf-8")
            if len(captions) > 64 * 1024:
                raise Refused(f"{folder}/{rel}: larger than 64 KB")
        elif rel.startswith("wallpapers/") and FILE_RE.fullmatch(rel[len("wallpapers/"):]):
            files["theme/" + rel] = _picture(path)
            pictures.append(rel[len("wallpapers/"):])
        else:
            raise Refused(f"{folder}/{rel}: not a file a theme may carry")
    if len(pictures) > MAX_PICTURES:
        raise Refused(f"{folder}: more than {MAX_PICTURES} wallpapers")
    if sum(len(b) for b in files.values()) > MAX_TOTAL:
        raise Refused(f"{folder}: pictures larger than {MAX_TOTAL // (1024 * 1024)} MB in all")
    for mood, names in (config.get("wallpaper_moods") or {}).items():
        missing = [n for n in names if n not in pictures]
        if missing:
            raise Refused(f"{folder}/config.json: wallpaper_moods.{mood} names pictures that are not in wallpapers/: "
                          + ", ".join(missing))
    digest = hashlib.sha256(json.dumps(config, sort_keys=True).encode())
    for name in sorted(files):
        digest.update(name.encode())
        digest.update(files[name])
    digest.update(captions.encode())
    return {"name": folder.name, "hash": digest.hexdigest(), "config": config,
            "wallpapers": {"single": single, "files": sorted(pictures), "captions": captions}, "files": files}


def script(theme):
    """theme.js for the package: data only, safe inside a classic script. No theme: built-in defaults."""
    data = {"name": "", "hash": "", "config": None, "wallpapers": None}
    if theme:
        data = {k: theme[k] for k in ("name", "hash", "config", "wallpapers")}
    text = json.dumps(data, ensure_ascii=True, sort_keys=True).replace("<", "\\u003c").replace(">", "\\u003e")
    return "/* Generated by cytv-webos build. Data only. */\nwindow.CYTV = window.CYTV || {};\nwindow.CYTV.theme = " + text + ";\n"


def resolve(name_or_path):
    """A theme argument: a folder path, or the name of a folder under themes/."""
    p = Path(name_or_path)
    if p.is_dir():
        return p
    if re.fullmatch(r"[a-z0-9-]{1,40}", name_or_path) and (THEMES / name_or_path).is_dir():
        return THEMES / name_or_path
    raise Refused(f"no theme {name_or_path!r}: pass a folder, or a name from themes/")
