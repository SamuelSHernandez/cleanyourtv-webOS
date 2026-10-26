"""cytv-webos: build, check, install, restore and Home integration for the webOS launcher.

Exit codes: 0 done and verified, 1 refused or failed, 2 outcome unknown or recovery incomplete.
"""
import argparse
import http.server
import json
from pathlib import Path
import sys

from .errors import Refused, TransportError
from . import addons, ares, build, capabilities, device, integration, inventory, journal, lifecycle, profiles, ssap, store, themes, tvinspect, watcher

ROOT = Path(__file__).resolve().parents[1]


def _ask(question):
    if not sys.stdin.isatty():
        return None
    try:
        answer = input(question).strip().lower()
    except EOFError:
        return None
    return True if answer in ("y", "yes") else False if answer in ("n", "no", "") else None


def _session(name, pair=False, repin=False):
    rec = device.load(name)
    return ssap.connect(name, rec["host"], pair=pair, repin=repin)


def _optional_session(name):
    if not ssap.load_creds(name):
        return None
    try:
        return _session(name)
    except (TransportError, Refused) as e:
        print(f"note: SSAP unavailable ({e}); continuing without it", file=sys.stderr)
        return None


def cmd_setup(a):
    device.save(a.device, a.host)
    print(f"saved {a.device}. The same name must be set up in LG's CLI: ares-setup-device (Developer Mode "
          "key server on), then ares-novacom --device {0} --getkey.".format(a.device))
    return 0


def cmd_check(a):
    device.load(a.device)
    t = ares.AresTransport(a.device)
    session = _optional_session(a.device)
    try:
        report = capabilities.collect(t, profiles.load_all(), session, build.launcher_info()["id"], a.device)
    finally:
        if session:
            session.close()
    print(json.dumps(report, indent=2, sort_keys=True) if a.json else capabilities.render(report))
    return 0 if not report["problems"] else 1


def cmd_pair(a):
    print("Accept the prompt on the TV screen (60 s)...")
    session = _session(a.device, pair=True, repin=a.repin)
    session.close()
    creds = ssap.load_creds(a.device)
    print(f"paired. TV certificate SHA-256 {creds['cert_sha256'][:16]}... pinned; the client key is stored "
          f"0600 in {ssap.creds_path(a.device)} and is never printed.")
    return 0


def cmd_sync(a):
    rec = device.load(a.device)
    t = ares.AresTransport(a.device)
    facts = t.device_info()
    profile = profiles.select(profiles.load_all(), facts.get("sdkVersion"))
    if not profile:
        raise Refused(f"no profile covers SDK {facts.get('sdkVersion')!r}")
    session = _session(a.device)
    try:
        record, missing = inventory.sync(a.device, rec["host"], session, profile)
    finally:
        session.close()
    print(f"{len(record['apps'])} apps synced ({missing} without an icon). Shortcuts: "
          + ", ".join(f"{k}={v or 'none'}" for k, v in record["shortcuts"].items()))
    print(f"next: cytv-webos build --device {a.device}")
    return 0


def _theme_dir(a):
    """--theme NAME|PATH, --theme none for the built-in look, or (install) the theme this TV last had."""
    t = getattr(a, "theme", None)
    if t == "none":
        return None
    if t:
        return themes.resolve(t)
    if getattr(a, "command", None) == "install" and getattr(a, "device", None):
        last = device.last_theme(a.device)
        return themes.resolve(last) if last else None
    return None


def cmd_build(a):
    path, digest, info = build.build(a.device, theme_dir=_theme_dir(a))
    print(f"{path}\nsha256 {digest}\n{info['id']} {info['version']}" + ("" if a.device else
          "\n(no --device: the package has no app list; the launcher will say so)"))
    return 0


def cmd_install(a):
    device.load(a.device)
    t = ares.AresTransport(a.device)
    theme_dir = None
    if a.ipk:
        ipk_path = Path(a.ipk)
    else:
        theme_dir = _theme_dir(a)
        ipk_path, _, _ = build.build(a.device if inventory.load(a.device) else None, theme_dir=theme_dir)
    session = _optional_session(a.device)
    foreground = (lambda: ssap.foreground_app(session)) if session else None
    try:
        result = lifecycle.install(a.device, t, ipk_path, profiles.load_all(), foreground=foreground,
                                   confirm=None if a.no_confirm else _ask, adopt=a.adopt,
                                   expect_id=build.launcher_info()["id"])
    finally:
        if session:
            session.close()
    if result.outcome == journal.APPLIED and not a.ipk:
        device.remember_theme(a.device, Path(theme_dir).resolve() if theme_dir else None)
    _print_result(result)
    return result.exit_code


def cmd_addon(a):
    rec = device.load(a.device) if a.action != "build" else None
    if a.action == "build":
        path, digest, info = addons.build(addons.resolve(a.target), build.BUILD)
        print(f"{path}\nsha256 {digest}\n{info['id']} {info['version']}")
        return 0
    t = ares.AresTransport(a.device)
    if a.action == "remove":
        result = lifecycle.restore(a.device, t, only=a.target)
        _print_result(result)
        return result.exit_code
    folder = addons.resolve(a.target)
    spec = addons.load(folder)
    if a.action == "install":
        path, digest, info = addons.build(folder, build.BUILD)
        result = lifecycle.install(a.device, t, path, profiles.load_all(), expect_id=info["id"], role="addon", adopt=a.adopt)
        _print_result(result)
        if result.outcome == journal.APPLIED:
            print("next: `cytv-webos sync` then `cytv-webos install` so Home lists it"
                  + ("; `cytv-webos addon approve` to show its card" if spec["card"] else ""))
        return result.exit_code
    if a.action == "approve":
        if not spec["card"]:
            raise Refused(f"{folder.name} declares no card")
        card = spec["card"]
        record = inventory.load(a.device) or {"apps": []}
        others = [x["title"] for x in record["apps"] if x["id"] != card["app"]]
        path, digest, _ = addons.build(folder, build.BUILD)
        print(f"Card from {card['app']} (package sha256 {digest[:12]}...):")
        print(f"  label   {card['label']}\n  caption {card.get('caption') or '-'}\n  accent  {card.get('accent') or '-'}")
        answer = (a.answer == "yes") if a.answer else _ask("Show this card on Home? [y/N] ")
        if answer is None:
            raise Refused("no answer: run it in a terminal, or pass --answer yes|no. Nothing was recorded.")
        addons.decide(a.device, card, "show" if answer else "hide", others, digest)
        print("decision: " + ("show" if answer else "hide") + ". It reaches the TV with the next `cytv-webos install`.")
        return 0
    return 2


def cmd_confirm(a):
    data = journal.load(a.device)
    launcher = data.get("launcher") if data else None
    if not launcher or launcher not in data["owned"] or journal.open_operation(data):
        raise Refused("no launcher installed by this tool is settled on this TV (run `cytv-webos status` first)")
    asked_about = dict(data["owned"][launcher])
    if getattr(a, "answer", None):
        answer = a.answer == "yes"   # the person typed the command after looking at the TV
    else:
        answer = _ask(f"Is CYTV Home {asked_about['version']} on the TV screen, showing your apps, and does the "
                      "remote move between tiles? [y/N] ")
    state = "user-confirmed" if answer is True else "user-denied" if answer is False else "unconfirmed"
    # The question may have been open for a while: write the answer only if the journal still describes
    # the version the person was asked about.
    with store.DeviceLock(a.device):
        data = journal.load(a.device)
        if not data or data["owned"].get(launcher) != asked_about or journal.open_operation(data):
            raise Refused("the installed launcher changed while the question was open; nothing was recorded")
        data["readiness"] = {"state": state, "version": asked_about["version"], "at": journal.now()}
        journal.save(a.device, data)
    print(f"readiness: {state}")
    return 0 if state == "user-confirmed" else 1


def cmd_status(a):
    t = None if a.offline else ares.AresTransport(a.device)
    try:
        data, state, result = lifecycle.status(a.device, t, settle=getattr(a, "settle", False))
    except Refused as e:
        open_op = journal.open_operation(journal.load(a.device) or {"operations": []})
        print(f"refused: {e}", file=sys.stderr)
        return lifecycle.EXIT_UNKNOWN if open_op else 1
    for m in result.messages:
        print(m)
    if not data:
        print("journal: none (nothing installed by this tool on this TV)")
    else:
        print(f"journal: baseline {data['baseline'].get('taken')} on {data['baseline'].get('tv', {}).get('modelName')}")
        owned = data.get("owned") or {}
        if not owned:
            print("owned:   nothing")
        for app_id, entry in sorted(owned.items(), key=lambda kv: kv[1]["role"] != "launcher"):
            print(f"owned:   {app_id} {entry['version']} ({entry['role']})")
        r = data.get("readiness") or {}
        print(f"ready:   {r.get('state', 'not checked')}" + (f" (version {r.get('version')})" if r else ""))
        for op in data["operations"][-5:]:
            print(f"  {op['started']} {op['kind']:<7} {op.get('app_id', '')} {op.get('version', '')} -> "
                  f"{op['outcome']} {op.get('detail', '')}")
    print(f"home:    {state['backend']} / {state['state']}" + (f" ({state['reason']})" if state.get("reason") else ""))
    open_op = journal.open_operation(data) if data else None
    return lifecycle.EXIT_UNKNOWN if open_op else 0


def cmd_restore(a):
    t = ares.AresTransport(a.device)
    result = lifecycle.restore(a.device, t, include_preexisting=a.include_preexisting,
                               force_conflict=a.force_conflict)
    _print_result(result)
    return result.exit_code


def cmd_home(a):
    if a.action == "status":
        r = integration.load(a.device)
        print(f"{r['backend']} / {r['state']}" + (f": {r['reason']}" if r.get("reason") else ""))
        return 0
    if a.action == "stop":
        integration.transition(a.device, "stop", "stopped by the owner")
        print("stopped. A running watcher exits within about a second; restarts stay stopped until "
              "`cytv-webos home resume`.")
        return 0
    if a.action == "resume":
        integration.transition(a.device, "resume", "resumed by the owner")
        print("resumed to inactive (manual mode). Run `cytv-webos home enable` to route Home again.")
        return 0
    if a.action == "deactivate":
        integration.transition(a.device, "deactivate", "deactivated by the owner")
        print("deactivated: manual mode.")
        return 0
    if a.action == "enable":
        return _home_enable(a)
    if a.action == "watch":
        rec = device.load(a.device)
        profile = _profile_for(a.device)
        return watcher.run(a.device, rec["host"], build.launcher_info()["id"], profile["home_app_ids"])
    return 2


def _profile_for(name):
    data = journal.load(name)
    pid = data["baseline"].get("profile") if data else None
    for p in profiles.load_all():
        if p["id"] == pid:
            return p
    raise Refused("install the launcher with this tool first; the profile is chosen at install")


def _home_enable(a):
    if a.backend != watcher.BACKEND:
        raise Refused(f"only {watcher.BACKEND} is implemented in this release")
    data = journal.load(a.device)
    if not journal.launcher_ready(data):
        raise Refused("the launcher's readiness is not confirmed for the installed version: install it and "
                      "confirm it works on the TV (`cytv-webos confirm-ready`) before routing Home to it")
    profile = _profile_for(a.device)
    if a.backend not in profile["backends"]:
        raise Refused(f"profile {profile['id']} has no {a.backend} backend")
    session = _session(a.device)
    try:
        apps = ssap.all_apps(session)
    finally:
        session.close()
    launcher_id = build.launcher_info()["id"]
    if launcher_id not in apps:
        raise Refused("the TV does not list the launcher; install it first")
    blocking = [c for c in profile["known_conflicts"] if c["kind"] in ("home-controller", "root") and c["id"] in apps]
    if blocking:
        raise Refused("another Home controller or root setup is installed, and two controllers must never run "
                      "at once: " + "; ".join(f"{c['id']} ({c['what']})" for c in blocking))
    integration.transition(a.device, "activate", "enabled by the owner", backend=a.backend)
    print("activating. Run `cytv-webos home watch --device {0}` and press Home on the remote; the integration "
          "becomes active once a redirect is confirmed. `cytv-webos home stop --device {0}` stops it."
          .format(a.device))
    return 0


def cmd_screenshot(a):
    device.load(a.device)
    app_id = build.launcher_info()["id"]
    if a.app:
        owned = (journal.load(a.device) or {}).get("owned") or {}
        if a.app not in owned:
            raise Refused(f"{a.app} is not an app this tool installed on this TV")
        app_id = a.app
    state, png = tvinspect.capture(a.device, app_id)
    out = Path(a.out)
    out.write_bytes(png)
    print(json.dumps(state, indent=1, sort_keys=True))
    print(f"screenshot: {out} (from the TV's own engine; the inspector tunnel is closed again)")
    return 0 if state.get("ready") else 1


def preview_handler(theme):
    """Static files from webos/, plus /preview/theme.js and the theme's pictures under /preview/theme/."""
    script = themes.script(theme).encode()
    files = theme["files"] if theme else {}

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT), **kwargs)

        def log_message(self, *args):
            pass

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            if host not in ("127.0.0.1", "localhost"):
                return self.send_error(403)   # a page from elsewhere reaching us by DNS rebinding
            if not path.startswith(("/preview/", "/launcher/", "/themes/")) or path.endswith("/") and path != "/preview/":
                return self.send_error(404)   # only what the preview needs; no build output, no listings
            if path == "/preview/theme.js":
                return self._send(script, "text/javascript")
            if path.startswith("/preview/theme/"):
                data = files.get(path[len("/preview/"):])
                if data is None:
                    return self.send_error(404)
                return self._send(data, "image/png" if path.endswith(".png") else "image/jpeg")
            return super().do_GET()

        def _send(self, body, kind):
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    return Handler


def cmd_preview(a):
    theme = themes.load(themes.resolve(a.theme)) if a.theme else None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), preview_handler(theme))
    print(f"preview: http://127.0.0.1:{a.port}/preview/  (simulated apps; theme: {theme['name'] if theme else 'built-in'}; Ctrl-C to stop)")
    print("query options: ?apps=0  ?fail=list  ?fail=launch  ?noshortcuts=1  ?storage=off  ?cards=1")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def _print_result(result):
    for m in result.messages:
        print(m)
    labels = {True: "yes", False: "NO", None: "not checked"}
    for stage in ("installed", "launched", "running", "foreground"):
        if stage in result.stages:
            print(f"{stage:<11} {labels.get(result.stages[stage], result.stages[stage])}")
    if "ready" in result.stages:
        print(f"{'ready':<11} {result.stages['ready']}")
    print(f"outcome     {result.outcome}")
    print("home        not changed by install (see `cytv-webos home status`)")


def parser():
    p = argparse.ArgumentParser(prog="cytv-webos", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    def dev(sp):
        sp.add_argument("--device", required=True, help="the ares device name of the TV")
        return sp

    s = dev(sub.add_parser("setup", help="remember a TV: its ares device name and address"))
    s.add_argument("--host", required=True)
    s.set_defaults(fn=cmd_setup)
    s = dev(sub.add_parser("check", help="read-only capability and compatibility report"))
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_check)
    s = dev(sub.add_parser("pair", help="pair with the TV's SSAP control channel (prompt on the TV)"))
    s.add_argument("--repin", action="store_true", help="accept a changed TV certificate")
    s.set_defaults(fn=cmd_pair)
    dev(sub.add_parser("sync", help="read the TV's apps and icons for the next build")).set_defaults(fn=cmd_sync)
    s = sub.add_parser("build", help="build the launcher IPK into webos/build/")
    s.add_argument("--device", help="bake this TV's synced app list into the package")
    s.add_argument("--theme", help="a theme folder, or a name from themes/, to bake in")
    s.set_defaults(fn=cmd_build)
    s = dev(sub.add_parser("install", help="install, launch and verify the launcher (manual mode)"))
    s.add_argument("--ipk", help="install this package instead of building one")
    s.add_argument("--theme", help="build with this theme folder (or a name from themes/); how a theme is pushed")
    s.add_argument("--adopt", action="store_true", help="install over a copy this tool did not install")
    s.add_argument("--no-confirm", action="store_true", help="do not ask whether the launcher works on screen")
    s.set_defaults(fn=cmd_install)
    s = dev(sub.add_parser("confirm-ready", help="record that the launcher works on the TV"))
    s.add_argument("--answer", choices=("yes", "no"), help="your answer, when no terminal prompt is possible")
    s.set_defaults(fn=cmd_confirm)
    s = dev(sub.add_parser("status", help="journal, readiness and Home state; settles unknown outcomes"))
    s.add_argument("--offline", action="store_true", help="do not contact the TV")
    s.add_argument("--settle", action="store_true", help="close an unknown outcome the TV cannot settle as failed")
    s.set_defaults(fn=cmd_status)
    s = dev(sub.add_parser("restore", help="stop Home integration and remove what this tool installed"))
    s.add_argument("--include-preexisting", action="store_true")
    s.add_argument("--force-conflict", action="store_true")
    s.set_defaults(fn=cmd_restore)
    s = dev(sub.add_parser("home", help="Home integration: status, enable, watch, stop, resume, deactivate"))
    s.add_argument("action", choices=("status", "enable", "watch", "stop", "resume", "deactivate"))
    s.add_argument("--backend", default=watcher.BACKEND)
    s.set_defaults(fn=cmd_home)
    s = sub.add_parser("addon", help="add-ons: build, install, approve (its card), remove")
    s.add_argument("action", choices=("build", "install", "approve", "remove"))
    s.add_argument("target", help="an add-on folder or name from addons/ (remove: its app id)")
    s.add_argument("--device", help="the ares device name of the TV (not needed for build)")
    s.add_argument("--adopt", action="store_true")
    s.add_argument("--answer", choices=("yes", "no"), help="approve: your answer, when no terminal prompt is possible")
    s.set_defaults(fn=cmd_addon)
    s = dev(sub.add_parser("screenshot", help="the launcher's screen and state from the TV's engine (opens LG's inspector for seconds)"))
    s.add_argument("--out", default="tv-home.png")
    s.add_argument("--app", help="an add-on this tool installed, instead of the launcher")
    s.set_defaults(fn=cmd_screenshot)
    s = sub.add_parser("preview", help="serve the launcher with simulated apps on 127.0.0.1")
    s.add_argument("--port", type=int, default=8642)
    s.add_argument("--theme", help="a theme folder, or a name from themes/")
    s.set_defaults(fn=cmd_preview)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return args.fn(args)
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    except TransportError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"error: {e.strerror or e}", file=sys.stderr)
        return 1
