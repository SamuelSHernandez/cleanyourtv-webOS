"""The Home integration state machine and the external watcher, against a scripted TV."""
import json
import unittest

from faketv import StateDir

from cytv_webos import integration, watcher
from cytv_webos.errors import LinkLost, Refused
from cytv_webos.ssap import SsapError

DEV = "tv"
LAUNCHER = "io.github.samuelshernandez.cytvwebos"
HOME = "com.webos.app.home"


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class ScriptedTV:
    """A fake SSAP session. Script items: ('fg', app), ('wait', s), ('lost',), ('call', fn)."""

    def __init__(self, script, clock, apps=None, launch_brings_front=True, launch_error=None):
        self.script = list(script)
        self.clock = clock
        self.apps = apps if apps is not None else {LAUNCHER: "0.1.0", HOME: "1.0"}
        self.launches = []
        self.launch_brings_front = launch_brings_front
        self.launch_error = launch_error
        self.closed = False

    def request(self, uri, payload=None):
        if uri.endswith("/listApps"):
            return {"returnValue": True, "apps": [{"id": a, "version": v} for a, v in self.apps.items()]}
        if uri == "ssap://system.launcher/launch":
            if self.launch_error:
                raise SsapError(self.launch_error)
            self.launches.append(payload["id"])
            if self.launch_brings_front:
                self.script.insert(0, ("fg", payload["id"]))
            return {"returnValue": True}
        raise AssertionError(uri)

    def subscribe(self, uri, payload=None):
        return "sub_1"

    def next_event(self, sub, timeout):
        while self.script:
            item = self.script.pop(0)
            if item[0] == "fg":
                self.clock.t += 0.5
                return {"appId": item[1], "returnValue": True}
            if item[0] == "wait":
                self.clock.t += item[1]
                return None
            if item[0] == "lost":
                raise LinkLost("the TV closed the connection")
            if item[0] == "call":
                item[1]()
        raise LinkLost("script finished")

    def close(self):
        self.closed = True


def run(sessions, clock, max_connections=None):
    queue = list(sessions)
    said = []

    def connect(device, host):
        if not queue:
            raise LinkLost("no more sessions")
        s = queue.pop(0)
        if isinstance(s, Exception):
            raise s
        return s

    code = watcher.run(DEV, "192.168.1.50", LAUNCHER, [HOME], connect=connect, monotonic=clock,
                       wall=lambda: clock.t, sleep=lambda s: None, say=said.append,
                       max_connections=max_connections or len(sessions))
    return code, said


class StateMachineTest(unittest.TestCase):
    def setUp(self):
        self.s = StateDir()
        self.s.__enter__()

    def tearDown(self):
        self.s.__exit__(None, None, None)

    def test_only_listed_transitions_are_allowed(self):
        self.assertEqual(integration.next_state("inactive", "activate"), "activating")
        self.assertEqual(integration.next_state("activating", "confirm"), "active")
        for state in integration.STATES:
            self.assertEqual(integration.next_state(state, "stop"), "stopped")
        for bad in [("inactive", "confirm"), ("stopped", "activate"), ("stopped", "confirm"),
                    ("failed", "activate"), ("failed", "confirm"), ("active", "resume"), ("unknown", "confirm")]:
            with self.assertRaises(Refused, msg=bad):
                integration.next_state(*bad)

    def test_stop_persists_and_only_resume_leaves_it(self):
        integration.transition(DEV, "activate", "t", backend="external-watcher")
        integration.transition(DEV, "stop", "emergency")
        self.assertEqual(integration.load(DEV)["state"], "stopped")   # read back as a new process would
        with self.assertRaises(Refused):
            integration.transition(DEV, "activate", "t", backend="external-watcher")
        integration.transition(DEV, "resume", "owner")
        r = integration.load(DEV)
        self.assertEqual((r["state"], r["backend"]), ("inactive", "manual"))

    def test_one_backend_at_a_time(self):
        integration.transition(DEV, "activate", "t", backend="external-watcher")
        with self.assertRaises(Refused):
            integration.transition(DEV, "activate", "t", backend="external-watcher")
        with self.assertRaises(Refused):
            integration.transition(DEV, "activate", "t", backend="manual")

    def test_stop_is_written_even_over_a_corrupt_record(self):
        path = integration.path_for(DEV)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("garbage")
        with self.assertRaises(Refused):
            integration.load(DEV)
        integration.transition(DEV, "stop", "emergency")
        self.assertEqual(integration.load(DEV)["state"], "stopped")

    def test_malformed_record_values_are_refused(self):
        path = integration.path_for(DEV)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "state": "turbo", "backend": "manual"}))
        with self.assertRaises(Refused):
            integration.load(DEV)


class PolicyTest(unittest.TestCase):
    def setUp(self):
        self.p = watcher.Policy(LAUNCHER, [HOME])
        self.t = 0.0

    def ev(self, app, dt=0.5):
        self.t += dt
        return self.p.on_foreground(app, self.t)[0]

    def test_initial_lg_home_is_left_alone(self):
        self.assertIsNone(self.ev(HOME))
        self.assertEqual(self.ev("netflix"), None)
        self.assertEqual(self.ev(HOME), "launch")

    def test_redirect_is_confirmed_by_the_launcher_in_front(self):
        self.ev("netflix")
        self.assertEqual(self.ev(HOME), "launch")
        self.assertEqual(self.ev(LAUNCHER), "confirm")

    def test_second_home_press_right_after_a_redirect_stays_on_lg_home(self):
        self.ev("netflix")
        self.ev(HOME)
        self.ev(LAUNCHER)
        self.assertIsNone(self.ev(HOME, dt=1.0))
        self.assertIsNone(self.ev(HOME, dt=10.0), "passthrough holds until another app opens")
        self.assertIsNone(self.ev("netflix"))
        self.assertEqual(self.ev(HOME), "launch")

    def test_duplicate_home_event_before_the_launcher_appears_does_not_launch_twice(self):
        self.ev("netflix")
        self.assertEqual(self.ev(HOME), "launch")
        self.assertIsNone(self.ev(HOME, dt=0.1))
        self.assertEqual(self.ev(LAUNCHER), "confirm")

    def test_unrelated_apps_and_settings_are_never_redirected(self):
        self.ev("netflix")
        for app in ("com.palm.app.settings", "com.webos.app.hdmi1", "com.webos.app.livetv", None):
            self.assertIsNone(self.ev(app))

    def test_redirect_storm_is_bounded(self):
        self.ev("netflix")
        actions = []
        for _ in range(watcher.MAX_REDIRECTS + 1):
            actions.append(self.ev(HOME, dt=4.0))
            self.ev(LAUNCHER)
            self.ev("netflix")
        self.assertEqual(actions[:watcher.MAX_REDIRECTS], ["launch"] * watcher.MAX_REDIRECTS)
        self.assertEqual(actions[-1], "fail")

    def test_quick_home_after_a_failed_launch_is_not_a_passthrough(self):
        self.ev("netflix")
        self.assertEqual(self.ev(HOME), "launch")
        self.p.launch_failed("refused")
        self.ev("netflix", dt=0.2)
        self.assertEqual(self.ev(HOME, dt=0.2), "launch")

    def test_launcher_that_never_appears_fails_after_bounded_attempts(self):
        self.ev("netflix")
        self.ev(HOME)
        self.t += watcher.CONFIRM_S + 1
        self.assertIsNone(self.p.on_tick(self.t)[0])
        self.ev("netflix")
        self.ev(HOME)
        self.t += watcher.CONFIRM_S + 1
        self.assertEqual(self.p.on_tick(self.t)[0], "fail")


def confirmed_install():
    """A launcher installed by the tool and confirmed by a person, as `home enable` requires."""
    from faketv import FakeTV, launcher_ipk
    from cytv_webos import lifecycle, profiles
    tv = FakeTV()
    ipk, _ = launcher_ipk()
    lifecycle.install(DEV, tv, ipk, profiles.load_all(), confirm=lambda q: True)
    return tv


class WatcherRunTest(unittest.TestCase):
    def setUp(self):
        self.s = StateDir()
        self.s.__enter__()
        self.clock = Clock()
        self.tv = confirmed_install()
        integration.transition(DEV, "activate", "test", backend="external-watcher")

    def tearDown(self):
        self.s.__exit__(None, None, None)

    def state(self):
        return integration.load(DEV)["state"]

    def test_redirect_confirms_activation(self):
        tv = ScriptedTV([("fg", "netflix"), ("fg", HOME)], self.clock)
        run([tv], self.clock)
        self.assertEqual(tv.launches, [LAUNCHER])
        self.assertEqual(self.state(), "active")
        self.assertTrue(tv.closed)

    def test_stop_written_while_running_is_obeyed_before_the_next_launch(self):
        tv = ScriptedTV([("fg", "netflix"), ("call", lambda: integration.transition(DEV, "stop", "owner")),
                         ("fg", HOME), ("fg", HOME)], self.clock)
        code, _ = run([tv], self.clock)
        self.assertEqual(code, 0)
        self.assertEqual(tv.launches, [])
        self.assertEqual(self.state(), "stopped")

    def test_a_restarted_watcher_does_not_undo_a_stop(self):
        integration.transition(DEV, "stop", "owner")
        tv = ScriptedTV([("fg", "netflix"), ("fg", HOME)], self.clock)
        code, said = run([tv], self.clock)
        self.assertEqual(code, 0)
        self.assertEqual(tv.launches, [])
        self.assertEqual(self.state(), "stopped")
        self.assertIn("nothing to do", said[0])

    def test_link_lost_after_launch_is_unknown_then_reconciled_back_to_activating(self):
        lost = ScriptedTV([("fg", "netflix"), ("fg", HOME)], self.clock, launch_brings_front=False)
        lost.script.append(("lost",))
        orig = lost.request

        def drop_after_launch(uri, payload=None):
            answer = orig(uri, payload)
            if uri == "ssap://system.launcher/launch":
                raise LinkLost("connection reset")
            return answer
        lost.request = drop_after_launch
        seen = []
        again = ScriptedTV([("call", lambda: seen.append(self.state())), ("fg", "netflix")], self.clock)
        run([lost, again], self.clock)
        self.assertEqual(seen, ["activating"], "reconnecting must reconcile unknown before acting")
        hist = [h["to"] for h in integration.load(DEV)["history"]]
        self.assertIn("unknown", hist)

    def test_launcher_gone_from_the_tv_fails_instead_of_looping(self):
        tv = ScriptedTV([("fg", HOME)], self.clock, apps={HOME: "1.0"})
        code, _ = run([tv], self.clock)
        self.assertEqual(code, 1)
        self.assertEqual(self.state(), "failed")
        self.assertIn("Developer Mode may have expired", integration.load(DEV)["reason"])

    def test_launch_refused_repeatedly_fails(self):
        tv = ScriptedTV([("fg", "netflix"), ("fg", HOME), ("fg", "netflix"), ("fg", HOME)], self.clock,
                        launch_error="app not found")
        code, _ = run([tv], self.clock)
        self.assertEqual(code, 1)
        self.assertEqual(self.state(), "failed")

    def test_unreachable_tv_backs_off_without_failing(self):
        code, said = run([LinkLost("standby"), LinkLost("standby"), LinkLost("standby")], self.clock)
        self.assertEqual(code, 0)
        self.assertEqual(self.state(), "activating")
        self.assertEqual(sum("retrying" in s for s in said), 3)

    def test_ssap_refusal_fails(self):
        code, _ = run([Refused("certificate changed")], self.clock)
        self.assertEqual(code, 1)
        self.assertEqual(self.state(), "failed")

    def test_restart_loop_is_bounded(self):
        codes = []
        for _ in range(watcher.MAX_STARTS + 1):
            code, _ = run([LinkLost("crash-like exit")], self.clock, max_connections=1)
            codes.append(code)
        self.assertEqual(codes[-1], 1)
        self.assertEqual(self.state(), "failed")

    def test_unreadable_record_mid_run_stops_without_acting(self):
        def corrupt():
            integration.path_for(DEV).write_text("{broken")
        tv = ScriptedTV([("fg", "netflix"), ("call", corrupt), ("fg", HOME)], self.clock)
        code, _ = run([tv], self.clock)
        self.assertEqual(code, 1)
        self.assertEqual(tv.launches, [])

    def test_a_new_unconfirmed_install_stops_routing_before_the_next_launch(self):
        from cytv_webos import journal
        data = journal.load(DEV)
        data["readiness"] = None          # what an install of another version leaves behind
        journal.save(DEV, data)
        tv = ScriptedTV([("fg", "netflix"), ("fg", HOME)], self.clock)
        code, _ = run([tv], self.clock)
        self.assertEqual(code, 1)
        self.assertEqual(tv.launches, [])
        self.assertEqual(self.state(), "failed")

    def test_an_open_operation_is_not_ready(self):
        from cytv_webos import journal
        data = journal.load(DEV)
        journal.begin(DEV, data, "install", app_id=LAUNCHER, version="0.2.0", sha256="x")
        tv = ScriptedTV([("fg", "netflix"), ("fg", HOME)], self.clock)
        run([tv], self.clock)
        self.assertEqual(tv.launches, [])

    def test_two_watchers_cannot_run_at_once(self):
        with watcher.WatcherLock(DEV):
            with self.assertRaises(Refused):
                run([ScriptedTV([], self.clock)], self.clock)


class EnableTest(unittest.TestCase):
    """`home enable`: the gate between a ready launcher and Home routing."""

    def setUp(self):
        self.s = StateDir()
        self.s.__enter__()
        from faketv import FakeTV, launcher_ipk
        from cytv_webos import device, lifecycle, profiles
        ipk, self.info = launcher_ipk()
        device.save(DEV, "192.168.1.50")
        self.result = lifecycle.install(DEV, FakeTV(), ipk, profiles.load_all(), confirm=lambda q: True)

    def tearDown(self):
        self.s.__exit__(None, None, None)

    def enable(self, apps):
        from unittest import mock
        import argparse
        from cytv_webos import cli

        class Session:
            def request(self, uri, payload=None):
                return {"returnValue": True, "apps": [{"id": a} for a in apps]}

            def close(self):
                pass
        import contextlib
        import io
        with mock.patch.object(cli, "_session", lambda name: Session()), contextlib.redirect_stdout(io.StringIO()):
            return cli._home_enable(argparse.Namespace(device=DEV, backend="external-watcher"))

    def test_another_home_controller_blocks_activation(self):
        for other in ("com.local.nativehome", "com.cleanyourtv.manager", "org.webosbrew.hbchannel"):
            with self.assertRaises(Refused) as ctx:
                self.enable([self.info["id"], other])
            self.assertIn(other, str(ctx.exception))
            self.assertEqual(integration.load(DEV)["state"], "inactive")

    def test_ready_launcher_and_no_conflict_activates(self):
        self.assertEqual(self.enable([self.info["id"], "netflix"]), 0)
        r = integration.load(DEV)
        self.assertEqual((r["state"], r["backend"]), ("activating", "external-watcher"))

    def test_launcher_missing_from_the_tv_blocks_activation(self):
        with self.assertRaises(Refused):
            self.enable(["netflix"])


class WatcherReachTest(unittest.TestCase):
    def test_watcher_uses_only_read_and_launch_calls(self):
        """The watcher's whole reach on the TV: list apps, read the foreground app, launch one id."""
        import inspect
        import re
        src = inspect.getsource(watcher)
        self.assertEqual(set(re.findall(r"ssap\.(\w+)\(", src)), {"all_apps", "launch"})
        self.assertEqual(re.findall(r"ssap://[\w./]+", src), [watcher.FOREGROUND])
        self.assertNotRegex(src, r"/dev/input|EVIOCGRAB|subprocess|os\.system")


if __name__ == "__main__":
    unittest.main()
