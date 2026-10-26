"""Stage the launcher, bake the TV's inventory into it, pack the IPK and verify the result."""
import io
import json
from pathlib import Path
import shutil
import struct
import tarfile
import gzip
import zlib

from .errors import Refused
from . import addons, inventory, ipk, themes

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "launcher"
BUILD = ROOT / "build"
ELF_MAGIC = b"\x7fELF"


def launcher_info():
    return ipk.read_appinfo(LAUNCHER)


def _png(size, pixel):
    """A small RGBA PNG from pixel(x, y) -> (r, g, b, a). Deterministic, standard library only."""
    rows = b"".join(b"\x00" + b"".join(bytes(pixel(x, y)) for x in range(size)) for y in range(size))

    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


def icon(size):
    """The app icon: a rounded tile with a simple house outline."""
    r = size * 0.22
    bg, fg = (31, 36, 43, 255), (95, 179, 255, 255)

    def inside_round(x, y):
        cx = min(max(x, r), size - 1 - r)
        cy = min(max(y, r), size - 1 - r)
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r

    def pixel(x, y):
        if not inside_round(x, y):
            return (0, 0, 0, 0)
        u, v = x / size, y / size
        roof = 0.22 <= v <= 0.52 and abs(u - 0.5) <= (v - 0.22) * 1.0 + 0.02 and abs(u - 0.5) >= (v - 0.22) * 1.0 - 0.07
        walls = 0.48 <= v <= 0.78 and (0.28 <= u <= 0.34 or 0.66 <= u <= 0.72)
        floor = 0.72 <= v <= 0.78 and 0.28 <= u <= 0.72
        return fg if (roof or walls or floor) else bg

    return _png(size, pixel)


def stage(device_inventory, out_dir=BUILD, theme=None, cards=None):
    """Copy launcher/ into a fresh staging folder with inventory.js, theme.js, icons, artwork and theme pictures."""
    info = launcher_info()
    staging = Path(out_dir) / "stage" / info["id"]
    if staging.exists():
        shutil.rmtree(staging)
    for rel, src in ipk.app_files(LAUNCHER):
        dst = staging / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    (staging / "icon.png").write_bytes(icon(80))
    (staging / "largeIcon.png").write_bytes(icon(130))
    record, art_src = device_inventory if device_inventory else (None, None)
    script = inventory.baked_script(record, info["id"], "cytv-webos build", cards=cards)
    (staging / "js" / "inventory.js").write_text(script, encoding="utf-8")
    (staging / "js" / "theme.js").write_text(themes.script(theme), encoding="utf-8")
    for rel, data in (theme["files"] if theme else {}).items():
        dst = staging / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    if record:
        art = staging / "art"
        art.mkdir(exist_ok=True)
        for a in record["apps"]:
            if a["art"]:
                src = Path(art_src) / a["art"]
                if src.is_file() and inventory.image_kind(src.read_bytes()[:8]):
                    shutil.copyfile(src, art / a["art"])
    return staging, info


def build(device=None, out_dir=BUILD, theme_dir=None):
    """Build the IPK; with a device, bake that TV's synced inventory and approved add-on cards; with a theme
    folder, bake the theme. Returns (path, sha256, info)."""
    theme = themes.load(theme_dir) if theme_dir else None
    cards = addons.shown_cards(device) if device else []
    baked = None
    if device:
        record = inventory.load(device)
        if record is None:
            raise Refused(f"no app inventory for {device}: run `cytv-webos sync --device {device}` first, "
                          "or build without --device for a package with no app list")
        baked = (record, inventory.inv_dir(device) / "art")
    staging, _ = stage(baked, out_dir, theme=theme, cards=cards)
    path, digest, info = ipk.build(staging, Path(out_dir))
    verify(path, expect_id=info["id"], expect_version=info["version"])
    return path, digest, info


def verify(path, expect_id=None, expect_version=None):
    """Check an IPK before it is installed. Returns its appinfo. Anything malformed is Refused."""
    try:
        return _verify(path, expect_id, expect_version)
    except Refused:
        raise
    except (OSError, EOFError, ValueError, KeyError, tarfile.TarError, zlib.error, UnicodeDecodeError) as e:
        raise Refused(f"{path}: not a readable webOS package ({type(e).__name__}: {e})")


def _verify(path, expect_id, expect_version):
    data = Path(path).read_bytes()
    members = ipk.read_members(data)
    names = [m[0] for m in members]
    if names != ["debian-binary", "control.tar.gz", "data.tar.gz"]:
        raise Refused(f"{path}: not a webOS package (members {names})")
    control_tar = tarfile.open(fileobj=io.BytesIO(gzip.decompress(members[1][1])))
    control = control_tar.extractfile("./control").read().decode()
    fields = dict(line.split(": ", 1) for line in control.splitlines() if ": " in line)
    if fields.get("Architecture") != "all":
        raise Refused(f"{path}: architecture {fields.get('Architecture')!r}; this release installs only "
                      "architecture-independent packages (no ABI detection yet)")
    package = fields.get("Package", "")
    if not ipk.APP_ID_RE.fullmatch(package):
        raise Refused(f"{path}: control names no valid package id")
    data_tar = tarfile.open(fileobj=io.BytesIO(gzip.decompress(members[2][1])))
    app_root = f"usr/palm/applications/{package}/"
    appinfo = None
    for member in data_tar.getmembers():
        name = member.name[2:] if member.name.startswith("./") else member.name
        if member.issym() or member.islnk() or ".." in name.split("/") or name.startswith("/"):
            raise Refused(f"{path}: unsafe entry {member.name!r}")
        if not member.isfile():
            continue
        if not name.startswith((app_root, f"usr/palm/packages/{package}/")):
            raise Refused(f"{path}: {member.name} is outside this app's folders")
        blob = data_tar.extractfile(member).read()
        if blob.startswith(ELF_MAGIC):
            raise Refused(f"{path}: {member.name} is a native binary; this release ships none")
        if name.rsplit("/", 1)[-1] in ipk.EXCLUDED_NAMES:
            raise Refused(f"{path}: {member.name} is a preview file and must not reach a TV")
        if name == app_root + "appinfo.json":
            appinfo = json.loads(blob)
    if not isinstance(appinfo, dict):
        raise Refused(f"{path}: no appinfo.json at the top of the app folder")
    if appinfo.get("type") != "web" or appinfo.get("main") != "index.html":
        raise Refused(f"{path}: not a web app whose main is index.html")
    if expect_id and appinfo.get("id") != expect_id:
        raise Refused(f"{path}: app id {appinfo.get('id')!r}; this tool installs only {expect_id!r}")
    if expect_version and appinfo.get("version") != expect_version:
        raise Refused(f"{path}: version {appinfo.get('version')!r}, expected {expect_version!r}")
    if package != appinfo.get("id") or fields.get("Version") != appinfo.get("version"):
        raise Refused(f"{path}: control and appinfo disagree on id or version")
    return appinfo
