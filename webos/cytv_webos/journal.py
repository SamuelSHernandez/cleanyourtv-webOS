"""The install journal: the state before the first change, and every operation's outcome.

Follows Gathin23/cleanyourtv@f592b6d (tools/recovery.py: the first record wins, never replaced) and
Razdva122/clean-your-tv-lg-webos@d5804f6 (cytv/state.py: a receipt before mutation).

One journal per TV (`<state root>/<device>/journal.json`). It can own several apps: the launcher and any add-ons
installed through this tool. For each app id, the baseline records whether the TV had it (and which version)
the first time this tool touched that id; that entry is never replaced, as upstream's recovery record only
gains names. Each operation is written as `pending` before it reaches the TV and moves to exactly one outcome.
"""
import time

from .errors import Refused
from . import store

VERSION = 1

# Outcomes an operation can end in.
NOT_ATTEMPTED = "not_attempted"
PENDING = "pending"                    # intent saved; the result has not been read back yet
APPLIED = "applied_verified"
REFUSED = "refused"
FAILED = "failed"
UNKNOWN = "unknown"                    # the link dropped after the change was sent
RESTORED = "restored_verified"
INCOMPLETE = "recovery_incomplete"
OUTCOMES = (NOT_ATTEMPTED, PENDING, APPLIED, REFUSED, FAILED, UNKNOWN, RESTORED, INCOMPLETE)
OPEN = (PENDING, UNKNOWN)              # must be reconciled before anything else runs
ROLES = ("launcher", "addon")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def path_for(device):
    return store.device_dir(device) / "journal.json"


def load(device):
    data = store.load_json(path_for(device), "install journal", VERSION)
    if data is None:
        return None
    base = data.get("baseline")
    if (not isinstance(data.get("operations"), list) or not isinstance(base, dict)
            or not isinstance(base.get("apps_before"), dict) or not isinstance(data.get("owned"), dict)):
        raise Refused(f"{path_for(device)}: install journal is missing its baseline, operations or owned apps; it "
                      "was left where it is. Move it aside deliberately to continue.")
    for op in data["operations"]:
        if not isinstance(op, dict) or op.get("outcome") not in OUTCOMES or op.get("kind") not in ("install", "remove"):
            raise Refused(f"{path_for(device)}: install journal holds an operation this version cannot read; "
                          "it was left where it is.")
    for app_id, entry in data["owned"].items():
        if not isinstance(entry, dict) or entry.get("role") not in ROLES or not isinstance(entry.get("version"), str):
            raise Refused(f"{path_for(device)}: install journal holds an owned app it cannot read ({app_id!r}).")
    return data


def new(device, tv, profile):
    return {"version": VERSION, "device": device, "created": now(),
            "baseline": {"taken": now(), "tv": tv, "profile": profile, "apps_before": {}},
            "operations": [], "owned": {}, "adopted": {}, "launcher": None, "readiness": None}


def record_before(data, app_id, installed):
    """The app's state before this tool first touched it. Only a new id is added; nothing is replaced."""
    before = data["baseline"]["apps_before"]
    if app_id not in before:
        before[app_id] = installed.get(app_id) if app_id in installed else None
        # An app present with an unreadable version is still present: record that, not absence.
        if app_id in installed and before[app_id] is None:
            before[app_id] = "unknown"
        return True
    return False


def was_present_before(data, app_id):
    return data["baseline"]["apps_before"].get(app_id) is not None or app_id in (data.get("adopted") or {})


def save(device, data):
    store.write_json(path_for(device), data)


def open_operation(data):
    for op in reversed(data["operations"]):
        if op["outcome"] in OPEN:
            return op
    return None


def begin(device, data, kind, **fields):
    """Save the intent before the TV is touched. If this write fails, nothing is sent."""
    op = {"kind": kind, "outcome": PENDING, "started": now(), "finished": None, "detail": ""}
    op.update(fields)
    data["operations"].append(op)
    save(device, data)
    return op


def finish(device, data, op, outcome, detail=""):
    if outcome not in OUTCOMES or outcome == PENDING:
        raise ValueError(outcome)
    op["outcome"] = outcome
    op["finished"] = now()
    op["detail"] = detail
    save(device, data)
    return op


def launcher_ready(data):
    """True when a person confirmed the launcher working, for the version this tool owns now, and nothing is open."""
    if not data or open_operation(data):
        return False
    launcher = data.get("launcher")
    owned = (data.get("owned") or {}).get(launcher) if launcher else None
    r = data.get("readiness")
    return bool(owned) and isinstance(r, dict) and r.get("state") == "user-confirmed" and r.get("version") == owned["version"]
