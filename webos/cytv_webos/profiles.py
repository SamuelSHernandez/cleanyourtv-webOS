"""Device profiles: versioned, validated JSON in webos/profiles/.

Pattern from lasharor/cleanyourtv-WebOS@5667cd5 (helper/tvprofile.js decide(), compat.json levels).

A profile holds the device-specific choices (which app ids are LG Home, which system apps the
shortcuts open, which installed apps conflict) and the hardware evidence for each backend. Passing
a profile's checks makes a TV eligible for a path; it does not certify the TV.
"""
import json
from pathlib import Path
import re

from .errors import Refused

SCHEMA = 1
PROFILE_DIR = Path(__file__).resolve().parents[1] / "profiles"
EVIDENCE_LEVELS = ("automated-tests-only", "experimental-hardware", "community-reported",
                   "maintainer-verified", "known-incompatible")
BACKENDS = ("manual", "external-watcher")
REQUIREMENTS = ("ssap-paired", "launcher-ready")
SHORTCUTS = ("inputs", "settings", "livetv")
CONFLICT_KINDS = ("home-controller", "launcher", "root")
APP_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
VERSION_RE = re.compile(r"\d+(\.\d+){0,3}")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _ids(value, where):
    if not isinstance(value, list) or not all(isinstance(v, str) and APP_ID_RE.fullmatch(v) for v in value):
        raise Refused(f"{where}: must be a list of app ids")
    return value


def validate(p, name="profile"):
    """Raise Refused naming the first problem; return the profile unchanged when valid."""
    if not isinstance(p, dict) or p.get("schema") != SCHEMA:
        raise Refused(f"{name}: schema must be {SCHEMA}")
    allowed = {"schema", "id", "description", "match", "browser_floor", "home_app_ids", "shortcut_candidates",
               "backends", "known_conflicts", "evidence"}
    extra = set(p) - allowed
    if extra:
        raise Refused(f"{name}: unknown keys {sorted(extra)}")
    if not isinstance(p.get("id"), str) or not re.fullmatch(r"[a-z0-9-]{3,64}", p["id"]):
        raise Refused(f"{name}: id must be 3-64 lowercase letters, digits or -")
    m = p.get("match")
    if not isinstance(m, dict) or set(m) != {"sdk_major_min", "sdk_major_max"}:
        raise Refused(f"{name}: match needs sdk_major_min and sdk_major_max")
    lo, hi = m["sdk_major_min"], m["sdk_major_max"]
    if not isinstance(lo, int) or not (hi is None or (isinstance(hi, int) and hi >= lo)):
        raise Refused(f"{name}: match bounds must be whole numbers with max >= min (max may be null)")
    if not _ids(p.get("home_app_ids"), f"{name}.home_app_ids"):
        raise Refused(f"{name}: home_app_ids may not be empty")
    sc = p.get("shortcut_candidates")
    if not isinstance(sc, dict) or set(sc) != set(SHORTCUTS):
        raise Refused(f"{name}: shortcut_candidates needs exactly {list(SHORTCUTS)}")
    for k in SHORTCUTS:
        _ids(sc[k], f"{name}.shortcut_candidates.{k}")
    b = p.get("backends")
    if not isinstance(b, dict) or "manual" not in b or not set(b) <= set(BACKENDS):
        raise Refused(f"{name}: backends must include manual and only {list(BACKENDS)}")
    for key, spec in b.items():
        if not isinstance(spec, dict) or spec.get("evidence") not in EVIDENCE_LEVELS:
            raise Refused(f"{name}.backends.{key}: evidence must be one of {list(EVIDENCE_LEVELS)}")
        req = spec.get("requires")
        if not isinstance(req, list) or not set(req) <= set(REQUIREMENTS):
            raise Refused(f"{name}.backends.{key}: requires must be a list from {list(REQUIREMENTS)}")
    for c in p.get("known_conflicts") or []:
        if not (isinstance(c, dict) and isinstance(c.get("id"), str) and APP_ID_RE.fullmatch(c["id"])
                and c.get("kind") in CONFLICT_KINDS and isinstance(c.get("what"), str)):
            raise Refused(f"{name}: each known conflict needs id, kind ({'/'.join(CONFLICT_KINDS)}) and what")
    if not isinstance(p.get("evidence"), list):
        raise Refused(f"{name}: evidence must be a list")
    for e in p["evidence"]:
        validate_evidence(e, name)
    return p


def validate_evidence(e, name):
    keys = {"model", "firmware", "sdk", "app_version", "backend", "level", "date", "checklist", "reporter", "notes"}
    if not isinstance(e, dict) or set(e) - keys or not {"model", "firmware", "app_version", "backend", "level", "date"} <= set(e):
        raise Refused(f"{name}: evidence entries need model, firmware, app_version, backend, level and date")
    if e["level"] not in EVIDENCE_LEVELS or e["backend"] not in BACKENDS:
        raise Refused(f"{name}: evidence level or backend is not a known value")
    if not VERSION_RE.fullmatch(str(e["app_version"])) or not DATE_RE.fullmatch(str(e["date"])):
        raise Refused(f"{name}: evidence app_version must be a version and date YYYY-MM-DD")
    if not re.fullmatch(r"[A-Za-z0-9 ._()/-]{2,40}", str(e["model"])) or not re.fullmatch(r"[0-9.]{2,20}", str(e["firmware"])):
        raise Refused(f"{name}: evidence model or firmware has characters a model or firmware does not use")


def load_all(directory=PROFILE_DIR):
    profiles = []
    for path in sorted(Path(directory).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise Refused(f"{path}: {e}")
        profiles.append(validate(data, path.name))
    if not profiles:
        raise Refused(f"no device profiles in {directory}")
    return profiles


def sdk_major(sdk_version):
    m = re.match(r"\s*(\d+)", sdk_version or "")
    return int(m.group(1)) if m else None


def select(profiles, sdk_version):
    """The profile for this SDK version, or None when no profile covers it (unsupported)."""
    major = sdk_major(sdk_version)
    if major is None:
        return None
    for p in profiles:
        lo, hi = p["match"]["sdk_major_min"], p["match"]["sdk_major_max"]
        if major >= lo and (hi is None or major <= hi):
            return p
    return None
