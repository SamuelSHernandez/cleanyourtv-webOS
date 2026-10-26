"""Regression tests for problems an independent review found in milestone 1 (2026-10-26)."""
import argparse
import contextlib
import io
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest
from unittest import mock

from faketv import FakeTV, StateDir, launcher_ipk, variant_ipk

from cytv_webos import capabilities, cli, integration, journal, lifecycle, profiles, store, watcher
from cytv_webos.errors import Refused, TransportError, scrub

DEV = "tv"
ROOT = Path(__file__).resolve().parents[1]


class Base(unittest.TestCase):
    def setUp(self):
        self.s = StateDir()
        self.root = self.s.__enter__()

    def tearDown(self):
        self.s.__exit__(None, None, None)


class ConfirmReadyRaceTest(Base):
    def test_an_install_during_the_question_is_not_overwritten(self):
        tv = FakeTV()
        ipk, info = launcher_ipk()
        lifecycle.install(DEV, tv, ipk, profiles.load_all(), confirm=None)
        newer, _ = variant_ipk(version="0.4.0")

        def answer_after_an_install(question):
            lifecycle.install(DEV, tv, newer, profiles.load_all(), confirm=None)
            return True
        with mock.patch.object(cli, "_ask", answer_after_an_install):
            with self.assertRaises(Refused):
                cli.cmd_confirm(argparse.Namespace(device=DEV))
        data = journal.load(DEV)
        self.assertEqual(data["owned"][info["id"]]["version"], "0.4.0", "the newer install's record survives")
        self.assertFalse(journal.launcher_ready(data))


class DeviceNameTest(Base):
    def test_no_command_can_escape_the_state_folder(self):
        for name in ("../x", "a/b", "", ".", "x" * 40):
            with self.assertRaises(Refused):
                store.device_dir(name)
        for args in (["home", "stop", "--device", "../x"], ["confirm-ready", "--device", "../x"],
                     ["home", "status", "--device", "../../etc"]):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(cli.main(args), 1)
            self.assertIn("device names are", err.getvalue())
        self.assertFalse((self.root.parent / "x").exists())


class ScrubTest(Base):
    def test_addresses_never_reach_reports(self):
        tv = FakeTV()

        def unreachable():
            raise TransportError("connect ECONNREFUSED 192.168.1.50:9922")
        tv.device_info = unreachable
        report = capabilities.collect(tv, profiles.load_all(), None, "x.y.z", DEV)
        self.assertNotIn("192.168.1.50", " ".join(report["problems"]))
        self.assertEqual(scrub("fe80::1ff:fe23:4567:890a and 10.0.0.2"), "<tv address> and <tv address>")


HOLDER = r'''
import sys, time
sys.path.insert(0, sys.argv[1])
from cytv_webos import watcher
with watcher.WatcherLock("tv"):
    print("held", flush=True)
    time.sleep(60)
'''


class LockTest(Base):
    def test_a_crashed_holder_leaves_no_stale_lock(self):
        if store.fcntl is None:
            self.skipTest("flock is POSIX-only; Windows uses a lock file the owner deletes")
        env = dict(os.environ, CYTV_WEBOS_HOME=str(self.root))
        p = subprocess.Popen([sys.executable, "-c", HOLDER, str(ROOT)], env=env, stdout=subprocess.PIPE, text=True)
        self.assertEqual(p.stdout.readline().strip(), "held")
        with self.assertRaises(Refused):
            with watcher.WatcherLock(DEV):
                pass
        p.send_signal(signal.SIGKILL)
        p.wait()
        p.stdout.close()
        with watcher.WatcherLock(DEV):
            pass

    def test_stop_and_a_watcher_transition_cannot_interleave(self):
        integration.transition(DEV, "activate", "t", backend="external-watcher")
        lock = store.ProcessLock(store.device_dir(DEV) / "integration.lock", "busy")
        with lock:
            started = time.monotonic()
            with mock.patch.object(integration, "LOCK_WAIT_S", 0.2):
                with self.assertRaises(Refused):
                    integration.transition(DEV, "stop", "owner")
            self.assertGreaterEqual(time.monotonic() - started, 0.2)
        integration.transition(DEV, "stop", "owner")
        self.assertEqual(integration.load(DEV)["state"], "stopped")


if __name__ == "__main__":
    unittest.main()
