"""Install, verify, restore and reconcile, against any transport with AresTransport's methods.

The verify-before-handover order follows Gathin23/cleanyourtv@f592b6d (launcher/build-and-install.sh).

The order is the recovery contract:
  1. validate the package and the TV before anything is sent;
  2. reconcile an operation a previous run left open (pending or unknown) by reading the TV;
  3. record the app's state before this tool first touched it, and the intent;
  4. apply one bounded operation;
  5. read the result back and record exactly one outcome.

The tool owns two kinds of app on a TV: the launcher (`role` "launcher") and add-ons ("addon"). Install takes
one package whose id must be the one the caller expects; restore removes every owned app (or one), each read
back on its own.

Stages after a launcher install are reported separately, because each proves something different:
installed (the TV lists this id and version), launched (the CLI accepted the launch), running (the TV lists it
as running), foreground (SSAP says it is the visible app), ready (a person saw the launcher working on the
screen). Home handling is not part of install at all (integration.py).
"""
import hashlib
from pathlib import Path
import time

from .errors import LinkLost, Refused, TransportError
from .ares import PairingError
from . import build, integration, journal, profiles
from .store import DeviceLock

EXIT_OK, EXIT_FAILED, EXIT_UNKNOWN = 0, 1, 2
FOREGROUND_TRIES = 8


class Result:
    def __init__(self):
        self.outcome = journal.NOT_ATTEMPTED
        self.stages = {}
        self.messages = []

    def say(self, text):
        self.messages.append(text)

    @property
    def exit_code(self):
        if self.outcome in (journal.UNKNOWN, journal.INCOMPLETE):
            return EXIT_UNKNOWN
        if self.outcome in (journal.FAILED, journal.REFUSED):
            return EXIT_FAILED
        if self.stages.get("ready") == "user-denied" or self.stages.get("launched") is False:
            return EXIT_FAILED
        return EXIT_OK


def _read_installed(transport, why):
    try:
        return transport.installed()
    except (TransportError, Refused) as e:
        raise Refused(f"{why}: the TV's app list could not be read ({e}). Nothing was changed.")


def _own(data, app_id, version, digest, role):
    data["owned"][app_id] = {"version": version, "sha256": digest, "role": role}
    if role == "launcher":
        data["launcher"] = app_id
        data["readiness"] = None


def _disown(data, app_id):
    data["owned"].pop(app_id, None)
    data.get("adopted", {}).pop(app_id, None)
    if data.get("launcher") == app_id:
        data["readiness"] = None


def reconcile(device, data, transport, result, settle=False):
    """Settle an open operation by reading the TV. Raises Refused when it cannot be settled, unless the owner
    passed settle=True (`status --settle`): then it is closed as failed, recording what the TV lists."""
    op = journal.open_operation(data)
    if not op:
        return
    installed = _read_installed(transport, f"a previous {op['kind']} ended with an unknown outcome")
    app_id = op.get("app_id")
    present, version = app_id in installed, installed.get(app_id)
    if op["kind"] == "install":
        if present and version == op.get("version") and op.get("previous_version") == version:
            # The same version before and after: the TV cannot say which package it holds. Not counted as applied.
            journal.finish(device, data, op, journal.FAILED,
                           "reconciled: the TV lists the same version as before; install again to be sure")
            result.say(f"previous install of {app_id} could not be confirmed (same version {version}); install again")
        elif present and version == op.get("version"):
            journal.finish(device, data, op, journal.APPLIED, "reconciled: the TV lists this version")
            _own(data, app_id, op["version"], op.get("sha256"), op.get("role", "launcher"))
            journal.save(device, data)
            result.say(f"previous install reconciled: {app_id} {version} is on the TV")
        elif not present:
            journal.finish(device, data, op, journal.FAILED, "reconciled: the app is not on the TV")
            result.say(f"previous install reconciled: {app_id} never arrived on the TV")
        elif "previous_version" in op and version == op["previous_version"]:
            journal.finish(device, data, op, journal.FAILED,
                           f"reconciled: the TV still has the version from before ({version})")
            result.say(f"previous install reconciled: {app_id} is still at {version}; the update did not land")
        elif settle:
            journal.finish(device, data, op, journal.FAILED, f"settled by the owner: the TV lists {version!r}")
            result.say(f"settled: the TV lists {app_id} {version}; restore will need --force-conflict to remove it")
        else:
            raise Refused(f"a previous install of {app_id} {op.get('version')} ended with an unknown outcome, and "
                          f"the TV now lists version {version!r}. Something else changed it. Check the TV, then run "
                          "`cytv-webos status --settle` to close this as failed. Nothing was changed.")
    else:
        if not present:
            journal.finish(device, data, op, journal.RESTORED, "reconciled: the app is gone from the TV")
            _disown(data, app_id)
            journal.save(device, data)
            result.say(f"previous removal reconciled: {app_id} is gone")
        else:
            journal.finish(device, data, op, journal.INCOMPLETE, "reconciled: the app is still on the TV")
            result.say(f"previous removal reconciled: {app_id} is still on the TV")


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def install(device, transport, ipk_path, profile_list, foreground=None, confirm=None, adopt=False, expect_id=None,
            role="launcher"):
    """Install and verify one package. `expect_id`: the only app id this call may install; any other package is
    refused. `foreground()` returns the foreground app id via SSAP (or raises); `confirm(question)` asks the person
    in front of the TV and returns True/False/None. Launch and readiness are checked for the launcher only."""
    if role not in journal.ROLES:
        raise Refused(f"unknown role {role!r}")
    result = Result()
    info = build.verify(ipk_path, expect_id=expect_id)   # 1. the package, before the TV is asked anything
    app_id, version, digest = info["id"], info["version"], _sha256(ipk_path)
    missing = transport.missing_tools()
    if missing:
        raise Refused("LG's webOS CLI is missing (" + ", ".join(missing) + "). Nothing was changed.")
    with DeviceLock(device):
        try:
            facts = transport.device_info()
        except PairingError:
            raise
        except (TransportError, Refused) as e:
            raise Refused(f"cannot read the TV's system information ({e}). Nothing was changed.")
        profile = profiles.select(profile_list, facts.get("sdkVersion"))
        if not profile:
            raise Refused(f"no profile covers this TV (SDK {facts.get('sdkVersion')!r}). Nothing was changed.")

        data = journal.load(device)
        if data:
            reconcile(device, data, transport, result)  # 2.
        installed = _read_installed(transport, "before installing")
        owned = data["owned"].get(app_id) if data else None
        if data and role == "launcher" and data.get("launcher") not in (None, app_id):
            raise Refused(f"this tool manages {data['launcher']} as the launcher on this TV, not {app_id}; it "
                          "installs only the launcher it owns. Nothing was changed.")
        if owned and owned["role"] != role:
            raise Refused(f"{app_id} is owned here as {owned['role']}, not {role}. Nothing was changed.")
        if app_id in installed and not owned and not adopt:
            raise Refused(f"{app_id} {installed[app_id] or ''} is already on the TV and this tool's journal does "
                          "not own it (another install, or a journal that was moved aside). Remove it, or pass "
                          "--adopt to install over it; restore will then leave it installed. Nothing was changed.")
        if owned and app_id in installed and installed[app_id] != owned["version"]:
            raise Refused(f"the TV has {app_id} {installed[app_id]}, but this tool last installed {owned['version']}; "
                          "something else changed it. Nothing was changed.")
        if data is None:
            data = journal.new(device, {k: facts.get(k) for k in ("modelName", "sdkVersion", "firmwareVersion")},
                               profile["id"])
        journal.record_before(data, app_id, installed)   # 3. once per app id, before any mutation
        if app_id in installed and not owned:
            data.setdefault("adopted", {})[app_id] = installed.get(app_id)
        elif app_id not in installed:
            data.setdefault("adopted", {}).pop(app_id, None)
        try:
            journal.save(device, data)
        except OSError as e:
            raise Refused(f"cannot save the install journal ({e}). Nothing was sent to the TV.")

        if owned and owned.get("sha256") == digest and installed.get(app_id) == version:
            result.outcome = journal.APPLIED
            result.stages["installed"] = True
            result.say(f"{app_id} {version} from this exact package is already installed; not reinstalling")
        else:
            try:
                # Readiness belongs to the launcher version on the TV, which this install is about to change; it is
                # cleared with the intent, so no Home routing can rely on it until a person confirms again.
                if role == "launcher":
                    data["readiness"] = None
                op = journal.begin(device, data, "install", app_id=app_id, version=version, sha256=digest, role=role,
                                   previous_version=installed.get(app_id))
            except OSError as e:
                raise Refused(f"cannot save the install intent ({e}). Nothing was sent to the TV.")
            send_error = None
            try:
                transport.install(ipk_path)     # 4.
            except LinkLost as e:
                journal.finish(device, data, op, journal.UNKNOWN, str(e))
                result.outcome = journal.UNKNOWN
                result.say(f"install outcome unknown: {e}. Run `cytv-webos status` once the TV answers.")
                return result
            except PairingError as e:
                journal.finish(device, data, op, journal.REFUSED, str(e))
                raise
            except (TransportError, Refused) as e:
                send_error = e
            try:
                after = transport.installed()   # 5. read back, even when the CLI reported an error
            except (TransportError, Refused) as e:
                journal.finish(device, data, op, journal.UNKNOWN, f"could not read back: {e}")
                result.outcome = journal.UNKNOWN
                result.say(f"install sent, but the result could not be read back ({e}). Run `cytv-webos status`.")
                return result
            if after.get(app_id) == version and send_error and op.get("previous_version") == version:
                # The TV lists the same version it had before, and the CLI reported an error: nothing shows the
                # new package landed (a rebuilt theme keeps the version), so this is no success.
                journal.finish(device, data, op, journal.FAILED, f"{send_error}; the TV still lists {version}")
                result.outcome = journal.FAILED
                result.stages["installed"] = False
                result.say(f"install failed: {send_error}")
                return result
            if after.get(app_id) == version:
                journal.finish(device, data, op, journal.APPLIED,
                               f"verified; the CLI reported: {send_error}" if send_error else "verified")
                _own(data, app_id, version, digest, role)
                journal.save(device, data)
                result.outcome = journal.APPLIED
                result.stages["installed"] = True
            else:
                why = str(send_error) if send_error else f"the TV lists {after.get(app_id, 'nothing')!r} after install"
                journal.finish(device, data, op, journal.FAILED, why)
                result.outcome = journal.FAILED
                result.stages["installed"] = False
                result.say(f"install failed: {why}")
                return result

        if role == "launcher":
            verify_launch(device, data, transport, app_id, version, result, foreground, confirm)
        return result


def verify_launch(device, data, transport, app_id, version, result, foreground=None, confirm=None, sleep=None):
    try:
        transport.launch(app_id)
        result.stages["launched"] = True
    except (TransportError, Refused) as e:
        result.stages["launched"] = False
        result.say(f"launch failed: {e}")
        return
    try:
        result.stages["running"] = app_id in transport.running()
    except (TransportError, Refused) as e:
        result.stages["running"] = None
        result.say(f"could not check whether it is running: {e}")
    if foreground:
        # Observed on a 50UQ7570PUJ (webOS 22): right after a launch the TV reports an empty foreground app
        # while the window comes up. Ask again for a few seconds before answering no.
        try:
            seen = None
            for attempt in range(FOREGROUND_TRIES):
                seen = foreground()
                if seen == app_id:
                    break
                (sleep or time.sleep)(1.0)
            result.stages["foreground"] = seen == app_id
            if seen != app_id:
                result.say(f"after {FOREGROUND_TRIES} s the TV reports {seen or 'no app'} in front")
        except Exception as e:  # SSAP is optional here; any failure is reported, not fatal
            result.stages["foreground"] = None
            result.say(f"could not check the foreground app over SSAP: {e}")
    else:
        result.stages["foreground"] = None
    answer = confirm("Is the CYTV Home launcher on the TV screen, showing your apps, and does the remote "
                     "move between tiles? [y/N] ") if confirm else None
    state = "user-confirmed" if answer is True else "user-denied" if answer is False else "unconfirmed"
    result.stages["ready"] = state
    data["readiness"] = {"state": state, "version": version, "at": journal.now()}
    journal.save(device, data)


def _worst(outcomes):
    for o in (journal.UNKNOWN, journal.INCOMPLETE, journal.FAILED):
        if o in outcomes:
            return o
    return journal.RESTORED


def restore(device, transport, include_preexisting=False, force_conflict=False, only=None):
    """Stop Home integration (when the launcher goes), remove what this tool installed, verify each is gone.
    `only`: remove just this owned app id (an add-on)."""
    result = Result()
    if only is None:
        # Home routing stops first, before anything that needs the TV or a readable journal, so a restore that is
        # refused further down still leaves Home alone.
        try:
            state = integration.load(device)
        except Refused:
            state = None
        if state is None or state["state"] not in ("inactive", "stopped"):
            integration.transition(device, "stop", "restore requested")
            result.say("Home integration stopped (persistent). A running watcher exits at its next check.")
    with DeviceLock(device):
        data = journal.load(device)
        if data is None:
            raise Refused("no install journal for this TV, so nothing is recorded as installed by this tool and "
                          "nothing will be removed. An app installed another way can be removed with "
                          "`ares-install --device <name> --remove <app id>`.")
        reconcile(device, data, transport, result)
        targets = [a for a in data["owned"] if only is None or a == only]
        if only is not None and not targets:
            raise Refused(f"{only} is not an app this tool installed on this TV. Nothing was changed.")
        if only is not None and data["owned"][only]["role"] == "launcher":
            raise Refused("that is the launcher: use `cytv-webos restore`, which stops Home routing first. "
                          "Nothing was changed.")
        if not targets:
            result.outcome = journal.RESTORED
            result.say("nothing installed by this tool is recorded on this TV; nothing to remove")
            return result
        # Add-ons first, the launcher last: Home stays usable for as long as possible.
        targets.sort(key=lambda a: data["owned"][a]["role"] == "launcher")
        installed = _read_installed(transport, "before removing")
        for app_id in targets:
            if installed.get(app_id) not in (None, data["owned"][app_id]["version"]) and app_id in installed \
                    and not force_conflict:
                raise Refused(f"the TV has {app_id} {installed[app_id]}, not the {data['owned'][app_id]['version']} this "
                              "tool installed; something else updated it. Nothing was removed (pass --force-conflict "
                              "to remove anyway).")
        outcomes = []
        for app_id in targets:
            outcomes.append(_remove_one(device, data, transport, app_id, installed, include_preexisting, result))
            if outcomes[-1] == journal.UNKNOWN:
                break   # the link is gone: nothing further is sent until it is reconciled
        result.outcome = _worst(outcomes)
        if result.outcome == journal.RESTORED and only is None:
            result.say("Press Home on the remote for LG's home screen.")
        return result


def _remove_one(device, data, transport, app_id, installed, include_preexisting, result):
    if journal.was_present_before(data, app_id) and not include_preexisting:
        result.say(f"{app_id} was on the TV before this tool installed over it; that earlier version cannot be put "
                   "back, so the app was left installed. Pass --include-preexisting to remove it anyway.")
        return journal.INCOMPLETE
    if app_id not in installed:
        _disown(data, app_id)
        journal.save(device, data)
        result.say(f"{app_id} is already gone from the TV")
        return journal.RESTORED
    op = journal.begin(device, data, "remove", app_id=app_id, version=installed[app_id])
    try:
        transport.close(app_id)
    except (TransportError, Refused):
        pass  # not running is fine; removal is what is verified
    send_error = None
    try:
        transport.remove(app_id)
    except LinkLost as e:
        journal.finish(device, data, op, journal.UNKNOWN, str(e))
        result.say(f"removal of {app_id}: outcome unknown ({e}). Run `cytv-webos status` once the TV answers.")
        return journal.UNKNOWN
    except PairingError as e:
        journal.finish(device, data, op, journal.REFUSED, str(e))
        raise
    except (TransportError, Refused) as e:
        send_error = e
    try:
        after = transport.installed()
    except (TransportError, Refused) as e:
        journal.finish(device, data, op, journal.UNKNOWN, f"could not read back: {e}")
        result.say(f"removal of {app_id} sent, but the result could not be read back ({e}). Run `cytv-webos status`.")
        return journal.UNKNOWN
    if app_id in after:
        journal.finish(device, data, op, journal.INCOMPLETE, str(send_error or "still listed after removal"))
        result.say(f"recovery incomplete: {app_id} is still on the TV ({send_error or 'still listed'})")
        return journal.INCOMPLETE
    journal.finish(device, data, op, journal.RESTORED, "verified absent")
    _disown(data, app_id)
    journal.save(device, data)
    result.say(f"{app_id} removed and verified absent.")
    return journal.RESTORED


def status(device, transport=None, settle=False):
    """The journal, the integration record and, with a transport, a reconcile of open operations."""
    result = Result()
    data = journal.load(device)
    if data and transport is not None:
        with DeviceLock(device):
            data = journal.load(device)
            reconcile(device, data, transport, result, settle=settle)
    return data, integration.load(device), result
