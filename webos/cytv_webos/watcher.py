"""Home backend: an external watcher on the computer (experimental).

Idea from OmkarK97/webos-vibehack@31a518a (home-watch.py: foreground subscription, a second Home
press as escape); the caps, the persistent stop and the reconcile are this project's.

How it routes Home: it subscribes to the TV's foreground app over SSAP and, when LG Home comes to the
front, launches the launcher. It never touches the TV's input devices, so it cannot capture or
hold the remote.

Failure boundary, stated plainly:
- The watcher is a process on the computer. If it hangs, crashes, or the computer sleeps, the TV
  behaves exactly as stock: Home shows LG Home. Nothing on the TV depends on the watcher.
- The only thing it can get wrong is launching the launcher when the owner wanted LG Home. That is
  bounded three ways, none of which depends on the watcher noticing a key gesture:
    * pressing Home again within PASSTHROUGH_S of a redirect leaves LG Home in front, until another
      app is opened (an on-TV escape that needs no computer);
    * at most MAX_REDIRECTS redirects per WINDOW_S and MAX_UNCONFIRMED launches that never reach
      the front; past either, the integration record moves to `failed` and the watcher stops acting;
    * at most MAX_STARTS process starts per STARTS_WINDOW_S, so a supervisor (launchd, systemd)
      restarting a crashing watcher cannot make a restart loop.
- `cytv-webos home stop` writes `stopped` to the integration record. The watcher re-reads the record
  before every launch and once a second, so it obeys within about a second, and a restarted watcher
  reads `stopped` and exits. Only `cytv-webos home resume` clears it.

Assumptions not yet proven on hardware (see docs/compatibility.md): that LG Home reports itself as
one of the profile's home_app_ids in getForegroundAppInfo, that the subscription delivers one
event per foreground change, and that system.launcher/launch brings a Developer Mode app to front.
"""
import collections
import json
import time

from .errors import LinkLost, Refused, TransportError
from . import integration, journal, ssap, store

BACKEND = "external-watcher"
FOREGROUND = "ssap://com.webos.applicationManager/getForegroundAppInfo"
PASSTHROUGH_S = 3.0
MAX_REDIRECTS, WINDOW_S = 5, 60.0
CONFIRM_S, MAX_UNCONFIRMED = 6.0, 2
MAX_STARTS, STARTS_WINDOW_S = 5, 600.0
BACKOFF_MAX_S = 60.0


class Policy:
    """Decides, from foreground events alone, when to launch the launcher. Pure; time is passed in."""

    def __init__(self, launcher_id, home_ids):
        self.launcher_id = launcher_id
        self.home_ids = set(home_ids)
        self.redirects = collections.deque()
        self.reset_connection()
        self.unconfirmed = 0

    def reset_connection(self):
        """A new subscription: its first event is the current state, not a Home press."""
        self.first = True
        self.passthrough = False
        self.last_redirect = None
        self.awaiting = None

    def on_foreground(self, app, now):
        """('launch'|'confirm'|'fail'|None, reason)."""
        first, self.first = self.first, False
        if app == self.launcher_id:
            self.passthrough = False
            if self.awaiting is not None:
                self.awaiting = None
                self.unconfirmed = 0
                return "confirm", "the launcher came to the front after a Home redirect"
            return None, "launcher in front"
        if app not in self.home_ids:
            self.passthrough = False
            return None, "another app in front"
        if first:
            return None, "LG Home was already in front when the watcher connected; left alone"
        if self.passthrough:
            return None, "LG Home chosen by the owner; left alone until another app opens"
        if self.last_redirect is not None and now - self.last_redirect < PASSTHROUGH_S:
            if self.awaiting is None:
                self.passthrough = True
                return None, "Home pressed again right after a redirect: staying on LG Home"
            return None, "duplicate LG Home event while the launcher is starting"
        while self.redirects and now - self.redirects[0] > WINDOW_S:
            self.redirects.popleft()
        if len(self.redirects) >= MAX_REDIRECTS:
            return "fail", f"{MAX_REDIRECTS} redirects within {int(WINDOW_S)} s; stopping to avoid fighting the owner"
        self.redirects.append(now)
        self.last_redirect = now
        self.awaiting = now
        return "launch", "LG Home came to the front"

    def on_tick(self, now):
        if self.awaiting is not None and now - self.awaiting > CONFIRM_S:
            return self._unconfirmed(f"the launcher did not come to the front within {CONFIRM_S:.0f} s")
        return None, ""

    def launch_failed(self, reason):
        return self._unconfirmed(f"the TV refused the launch ({reason})")

    def _unconfirmed(self, reason):
        # The launcher never reached the front, so a quick Home press after this is not the owner
        # leaving the launcher for LG Home: forget the redirect instead of opening the passthrough.
        self.awaiting = None
        self.last_redirect = None
        self.unconfirmed += 1
        if self.unconfirmed >= MAX_UNCONFIRMED:
            return "fail", f"{reason}, {self.unconfirmed} times in a row (Developer Mode may have expired)"
        return None, reason


def _starts_path(device):
    return store.device_dir(device) / "watcher-starts.json"


def record_start(device, now_wall):
    """Count this start. Returns False when starts are looping (too many in the window)."""
    path = _starts_path(device)
    try:
        starts = json.loads(path.read_text()).get("starts", [])
        starts = [float(s) for s in starts if isinstance(s, (int, float))]
    except (OSError, ValueError, AttributeError):
        starts = []
    starts = [s for s in starts if now_wall - s < STARTS_WINDOW_S] + [now_wall]
    store.write_json(path, {"version": 1, "starts": starts[-20:]})
    return len(starts) <= MAX_STARTS


def WatcherLock(device):
    """One watcher per TV. Separate from the install lock so `restore` can run while it is up."""
    return store.ProcessLock(store.device_dir(device) / "watcher.lock",
                             "a watcher is already running for this TV")


def run(device, host, launcher_id, home_ids, connect=ssap.connect, monotonic=time.monotonic,
        wall=time.time, sleep=time.sleep, say=print, max_connections=None):
    """Run until the record says stop, the backend fails, or max_connections (tests) is reached.
    Returns a process exit code: 0 stopped or deactivated, 1 failed."""
    with WatcherLock(device):
        record = integration.load(device)
        if record["backend"] != BACKEND or record["state"] not in ("activating", "active", "unknown"):
            say(f"Home integration is {record['state']} ({record['backend']}); the watcher has nothing to do.")
            return 0
        if not record_start(device, wall()):
            integration.transition(device, "fail", f"watcher started more than {MAX_STARTS} times in "
                                   f"{int(STARTS_WINDOW_S)} s")
            say("too many watcher starts in a short time; Home integration moved to failed.")
            return 1
        policy = Policy(launcher_id, home_ids)
        backoff, connections = 2.0, 0
        while max_connections is None or connections < max_connections:
            connections += 1
            record = integration.load(device)
            if record["backend"] != BACKEND or record["state"] not in ("activating", "active", "unknown"):
                say(f"Home integration is {record['state']}; watcher exiting.")
                return 0
            session = None
            try:
                session = connect(device, host)
                apps = ssap.all_apps(session)
                if launcher_id not in apps:
                    integration.transition(device, "fail", "the launcher is not installed on the TV (Developer "
                                           "Mode may have expired, which removes sideloaded apps)")
                    say("the launcher is not on the TV; Home integration moved to failed.")
                    return 1
                sub = session.subscribe(FOREGROUND)
                if record["state"] == "unknown":
                    integration.transition(device, "reconciled", "the TV answers again; confirming Home anew")
                policy.reset_connection()
                backoff = 2.0
                code = _listen(device, session, sub, policy, launcher_id, apps, monotonic, say)
                if code is not None:
                    return code
            except Refused as e:
                try:
                    integration.transition(device, "fail", f"refused: {e}")
                except Refused:
                    pass   # the record itself is unreadable: acting on it is exactly what must not happen
                say(f"refused ({e}); the watcher stops acting.")
                return 1
            except (TransportError, OSError) as e:
                say(f"TV not reachable ({e}); retrying in {backoff:.0f} s (standby looks like this too).")
            finally:
                if session is not None:
                    session.close()
            sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX_S)
        return 0


def _listen(device, session, sub, policy, launcher_id, apps, monotonic, say):
    """Handle events until the link drops (returns None) or the watcher must exit (returns a code)."""
    while True:
        payload = session.next_event(sub, 1.0)
        record = integration.load(device)
        if record["backend"] != BACKEND or record["state"] not in ("activating", "active"):
            say(f"Home integration is {record['state']}; watcher exiting.")
            return 0
        now = monotonic()
        if payload is None:
            action, reason = policy.on_tick(now)
        else:
            app = payload.get("appId") if isinstance(payload, dict) else None
            action, reason = policy.on_foreground(app if isinstance(app, str) else None, now)
        if action == "launch":
            if not journal.launcher_ready(journal.load(device)):
                reason = ("the launcher on the TV is not the version a person confirmed (a new install, or an "
                          "operation whose outcome is still unknown)")
                integration.transition(device, "fail", reason)
                say(f"{reason}. Home integration moved to failed; confirm the launcher, then resume and enable.")
                return 1
            try:
                ssap.launch(session, launcher_id, apps)
            except LinkLost:
                integration.transition(device, "lost", "link lost right after a launch was sent")
                raise
            except TransportError as e:
                action, reason = policy.launch_failed(str(e))
        if action == "confirm":
            if record["state"] == "activating":
                integration.transition(device, "confirm", reason)
                say("Home routing confirmed: the launcher came to the front after LG Home.")
        elif action == "fail":
            integration.transition(device, "fail", reason)
            say(f"{reason}. Home integration moved to failed; `cytv-webos home resume` to start over.")
            return 1
