"""Regression tests for the second review (parity round, 2026-10-26)."""
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest import mock

from faketv import FakeTV, StateDir, launcher_ipk, variant_ipk

from cytv_webos import addons, cli, integration, journal, lifecycle, profiles, themes, tvinspect
from cytv_webos.errors import Refused, TransportError

DEV = "tv"


class SameVersionReinstallTest(unittest.TestCase):
    def setUp(self):
        self.s = StateDir()
        self.s.__enter__()
        p = mock.patch.object(lifecycle.time, "sleep")
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.s.__exit__(None, None, None)

    def test_a_rejected_rebuild_of_the_same_version_is_a_failure(self):
        tv = FakeTV()
        ipk, info = launcher_ipk()
        lifecycle.install(DEV, tv, ipk, profiles.load_all(), confirm=lambda q: True)
        before = journal.load(DEV)["owned"][info["id"]]["sha256"]
        rebuilt, _ = variant_ipk(version=info["version"])          # same version, different bytes (a new theme)
        tv.faults["install_rejected"] = True
        r = lifecycle.install(DEV, tv, rebuilt, profiles.load_all())
        self.assertEqual(r.outcome, journal.FAILED)
        self.assertEqual(journal.load(DEV)["owned"][info["id"]]["sha256"], before, "the package that never landed is not owned")

    def test_an_unknown_same_version_reinstall_is_not_reconciled_as_applied(self):
        tv = FakeTV()
        ipk, info = launcher_ipk()
        lifecycle.install(DEV, tv, ipk, profiles.load_all(), confirm=lambda q: True)
        rebuilt, _ = variant_ipk(version=info["version"])
        tv.faults["link_lost_before_install"] = True
        self.assertEqual(lifecycle.install(DEV, tv, rebuilt, profiles.load_all()).outcome, journal.UNKNOWN)
        tv.faults.clear()
        lifecycle.status(DEV, tv)
        self.assertEqual(journal.load(DEV)["operations"][-1]["outcome"], journal.FAILED)

    def test_a_dead_end_can_be_settled_on_purpose(self):
        tv = FakeTV()
        ipk, info = launcher_ipk()
        lifecycle.install(DEV, tv, ipk, profiles.load_all(), confirm=lambda q: True)
        newer, _ = variant_ipk(version="0.5.0")
        tv.faults["link_lost_before_install"] = True
        lifecycle.install(DEV, tv, newer, profiles.load_all())
        tv.faults.clear()
        tv.installed_apps[info["id"]] = "9.9.9"                   # something else changed it meanwhile
        with self.assertRaises(Refused) as ctx:
            lifecycle.status(DEV, tv)
        self.assertIn("--settle", str(ctx.exception))
        lifecycle.status(DEV, tv, settle=True)
        self.assertIsNone(journal.open_operation(journal.load(DEV)))
        with self.assertRaises(Refused):
            lifecycle.restore(DEV, tv)                             # still a conflict...
        self.assertEqual(lifecycle.restore(DEV, tv, force_conflict=True).outcome, journal.RESTORED)   # ...unless forced

    def test_the_launcher_cannot_be_removed_as_an_addon(self):
        tv = FakeTV()
        ipk, info = launcher_ipk()
        lifecycle.install(DEV, tv, ipk, profiles.load_all(), confirm=lambda q: True)
        integration.transition(DEV, "activate", "t", backend="external-watcher")
        with self.assertRaises(Refused):
            lifecycle.restore(DEV, tv, only=info["id"])
        self.assertIn(info["id"], tv.installed_apps)


class InspectTimeoutTest(unittest.TestCase):
    def test_a_silent_inspector_is_closed_at_the_deadline(self):
        class Silent:
            def __init__(self, *a, **k):
                self.stdout = io.StringIO()      # never prints a tunnel line
                self.terminated = False
                r, w = os.pipe()
                self.stdout = os.fdopen(r)       # a pipe that stays open and silent
                self._w = w

            def terminate(self):
                self.terminated = True
                os.close(self._w)

            def wait(self, t):
                return 0

            def poll(self):
                return None
        made = []

        def popen(*a, **k):
            made.append(Silent())
            return made[-1]
        started = time.monotonic()
        with self.assertRaises(TransportError):
            tvinspect.capture(DEV, "x.y.z", popen=popen, timeout=0.5)
        self.assertLess(time.monotonic() - started, 5)
        self.assertTrue(made[0].terminated, "the tunnel is always closed")


class ThemeAndCardEdgesTest(unittest.TestCase):
    def folder(self):
        d = Path(tempfile.mkdtemp()) / "t"
        d.mkdir()
        (d / "config.json").write_text("{}")
        return d

    def test_a_linked_wallpapers_folder_is_refused_and_dotfiles_are_skipped(self):
        d = self.folder()
        outside = Path(tempfile.mkdtemp())
        shutil.copy(themes.THEMES / "aurora" / "wallpaper.png", outside / "001.png")
        os.symlink(outside, d / "wallpapers")
        with self.assertRaises(Refused):
            themes.load(d)
        e = self.folder()
        (e / ".DS_Store").write_bytes(b"\0\0\0\1Bud1")
        themes.load(e)

    def test_build_and_tv_agree_on_digits_and_lengths(self):
        schema = themes.schema()
        self.assertFalse(themes.check(schema["app_keys"], ["٤٠٣:netflix"]), "Arabic-Indic digits")
        self.assertFalse(themes.check(schema["greeting_name"], ["x"]))
        self.assertFalse(themes.check(schema["greeting_name"], "\U0001F600" * 21), "42 UTF-16 units > 40")
        self.assertTrue(themes.check(schema["greeting_name"], "\U0001F600" * 20))

    def test_card_fields_must_be_strings_when_present(self):
        for bad in ({"caption": None}, {"caption": False}, {"caption": 0}, {"accent": None}):
            with self.assertRaises(Refused, msg=bad):
                addons.validate_card(dict({"spec": 1, "label": "Retro"}, **bad), "a.b.c")

    def test_approve_without_an_answer_records_nothing(self):
        with StateDir():
            from cytv_webos import device
            device.save(DEV, "192.168.1.50")
            import argparse
            with mock.patch.object(cli, "_ask", lambda q: None), mock.patch.object(cli.ares, "AresTransport", lambda d: None):
                with self.assertRaises(Refused):
                    cli.cmd_addon(argparse.Namespace(action="approve", target="night-clock", device=DEV, adopt=False, answer=None))
            self.assertEqual(addons.decisions(DEV), [])


class PreviewServerTest(unittest.TestCase):
    def test_serves_only_the_preview_and_refuses_other_hosts(self):
        import http.server
        import threading
        import urllib.request
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), cli.preview_handler(None))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]

        def get(path, host=None):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
            if host:
                req.add_header("Host", host)
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                return e.code
        self.assertEqual(get("/preview/"), 200)
        self.assertEqual(get("/preview/theme.js"), 200)
        self.assertEqual(get("/launcher/js/app.js"), 200)
        self.assertEqual(get("/build/"), 404)
        self.assertEqual(get("/cytv_webos/ssap.py"), 404)
        self.assertEqual(get("/launcher/"), 404, "no directory listings")
        self.assertEqual(get("/preview/", host="evil.example"), 403)


if __name__ == "__main__":
    unittest.main()
