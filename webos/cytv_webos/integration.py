"""The Home-integration state machine and its persistent record.

The stop latch that only an explicit action clears follows Razdva122/clean-your-tv-lg-webos@d5804f6
(native/app/native.js, state/blocked) and lasharor/cleanyourtv-WebOS@5667cd5 (the DISABLE file).

Exactly one backend may own Home at a time. The record lives on the computer
(`<state root>/<device>/integration.json`) and is the single source of truth for every backend
process: a watcher reads it before each action, so a stop written here takes effect without
talking to the watcher, and a restarted watcher (launchd, systemd, a reboot) reads the stop too.

States and the only transitions allowed:

    inactive  --activate-->  activating   (launcher readiness confirmed, backend eligible)
    activating --confirm-->  active       (the backend demonstrated it routes Home)
    activating --fail----->  failed
    active    --fail----->   failed       (bounded attempts exhausted)
    active    --lost------>  unknown      (link lost after an action whose result was not seen)
    activating --lost----->  unknown
    unknown   --reconciled-> activating   (the TV answered again; Home routing must be confirmed anew)
    unknown   --fail----->   failed
    any       --stop------>  stopped      (emergency or user stop; survives restarts)
    stopped   --resume--->   inactive     (explicit user action only)
    failed    --resume--->   inactive     (explicit user action only)
    inactive  --deactivate-> inactive

Nothing moves out of `stopped` or `failed` except `resume`, and only the CLI's `home resume`
command calls it. A watcher never calls `resume`.
"""
import time

from .errors import Refused
from . import store

VERSION = 1
STATES = ("inactive", "activating", "active", "unknown", "failed", "stopped")
BACKENDS = ("manual", "external-watcher")
LOCK_WAIT_S = 5.0

TRANSITIONS = {
    ("inactive", "activate"): "activating",
    ("activating", "confirm"): "active",
    ("activating", "fail"): "failed",
    ("active", "fail"): "failed",
    ("active", "lost"): "unknown",
    ("activating", "lost"): "unknown",
    ("unknown", "reconciled"): "activating",
    ("unknown", "fail"): "failed",
    ("stopped", "resume"): "inactive",
    ("failed", "resume"): "inactive",
    ("inactive", "deactivate"): "inactive",
    ("activating", "deactivate"): "inactive",
    ("active", "deactivate"): "inactive",
    ("unknown", "deactivate"): "inactive",
}


def next_state(state, event):
    """The state after `event`, or Refused when the transition is not allowed."""
    if event == "stop":
        return "stopped"
    key = (state, event)
    if key not in TRANSITIONS:
        raise Refused(f"Home integration is {state}; '{event}' is not allowed from there.")
    return TRANSITIONS[key]


def path_for(device):
    return store.device_dir(device) / "integration.json"


def default_record():
    return {"version": VERSION, "state": "inactive", "backend": "manual", "reason": "",
            "updated": None, "history": []}


def load(device):
    record = store.load_json(path_for(device), "Home integration record", VERSION)
    if record is None:
        return default_record()
    if record.get("state") not in STATES or record.get("backend") not in BACKENDS:
        raise Refused(f"{path_for(device)}: unknown state or backend in the Home integration record; "
                      "it was left where it is. Run `cytv-webos home stop` to write a safe record.")
    return record


def transition(device, event, reason, backend=None):
    """Apply one event and persist it. A stop is written even over an unreadable record.

    Read, change and write happen under a lock, so a watcher's transition cannot overwrite a stop
    written at the same moment by `home stop`.
    """
    with store.ProcessLock(store.device_dir(device) / "integration.lock",
                           "the Home integration record is busy; try again", wait=LOCK_WAIT_S):
        return _transition(device, event, reason, backend)


def _transition(device, event, reason, backend):
    try:
        record = load(device)
    except Refused:
        if event != "stop":
            raise
        record = default_record()
    new = next_state(record["state"], event)
    if event == "activate":
        if backend not in BACKENDS or backend == "manual":
            raise Refused(f"cannot activate backend {backend!r}")
        if record["backend"] not in ("manual", backend) and record["state"] != "inactive":
            raise Refused(f"{record['backend']} still owns Home; deactivate it first.")
        record["backend"] = backend
    elif event in ("deactivate", "resume"):
        record["backend"] = "manual"
    record["history"] = (record.get("history") or [])[-19:] + [
        {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "from": record["state"], "event": event,
         "to": new, "reason": reason}]
    record["state"] = new
    record["reason"] = reason
    record["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    store.write_json(path_for(device), record)
    return record


def may_act(record, backend):
    """Whether `backend` may route Home right now. Only an active or activating record says yes."""
    return record["backend"] == backend and record["state"] in ("activating", "active")
