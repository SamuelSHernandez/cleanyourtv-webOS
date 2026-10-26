"""Install, verify, restore and reconcile against a simulated TV, with the failures a real TV
cannot be made to produce on demand."""
import json
import os
from pathlib import Path
import unittest
from unittest import mock

from faketv import FakeTV, StateDir, launcher_ipk, variant_ipk

from cytv_webos import integration, journal, lifecycle, profiles, store
from cytv_webos.ares import PairingError
from cytv_webos.errors import Refused

DEV = "tv"


def yes(_question):
    return True


class Base(unittest.TestCase):
    def setUp(self):
        self.state = StateDir()
        self.root = self.state.__enter__()
        sleeping = mock.patch.object(lifecycle.time, "sleep")   # no test waits for a real TV
        sleeping.start()
        self.addCleanup(sleeping.stop)
        self.ipk, self.info = launcher_ipk()
        self.app = self.info["id"]
        self.profiles = profiles.load_all()

    def tearDown(self):
        self.state.__exit__(None, None, None)

    def install(self, tv, **kw):
        kw.setdefault("confirm", yes)
        return lifecycle.install(DEV, tv, self.ipk, self.profiles, **kw)

    def journal(self):
        return journal.load(DEV)


class InstallTest(Base):
    def test_install_records_baseline_then_verifies_each_stage(self):
        tv = FakeTV()
        r = self.install(tv, foreground=lambda: self.app)
        self.assertEqual(r.outcome, journal.APPLIED)
        self.assertEqual(r.stages, {"installed": True, "launched": True, "running": True,
                                    "foreground": True, "ready": "user-confirmed"})
        self.assertEqual(r.exit_code, 0)
        j = self.journal()
        self.assertEqual(j["baseline"]["apps_before"], {self.app: None})
        self.assertEqual(j["baseline"]["tv"], {"modelName": "OLED55C3", "sdkVersion": "8.2.0",
                                               "firmwareVersion": "33.21.71"})
        self.assertEqual(j["owned"][self.app]["version"], self.info["version"])
        self.assertEqual((j["launcher"], j["owned"][self.app]["role"]), (self.app, "launcher"))
        self.assertTrue(journal.launcher_ready(j))
        # The intent was on disk before the TV saw the install.
        self.assertEqual([op["outcome"] for op in j["operations"]], [journal.APPLIED])

    def test_rejected_installation_fails_without_launch_and_keeps_baseline_for_retry(self):
        tv = FakeTV(install_rejected=True)
        r = self.install(tv)
        self.assertEqual(r.outcome, journal.FAILED)
        self.assertEqual(r.exit_code, 1)
        self.assertNotIn(f"launch:{self.app}", tv.calls)
        self.assertEqual(self.journal()["operations"][-1]["outcome"], journal.FAILED)
        first = self.journal()["baseline"]
        tv.faults.clear()
        tv.installed_apps["something.else"] = "1.0.0"   # the TV changed in between
        r2 = self.install(tv)
        self.assertEqual(r2.outcome, journal.APPLIED)
        self.assertEqual(self.journal()["baseline"], first, "a retry must not replace the original baseline")

    def test_full_storage_is_a_failure_with_the_reason(self):
        r = self.install(FakeTV(storage_full=True))
        self.assertEqual(r.outcome, journal.FAILED)
        self.assertIn("not enough space", self.journal()["operations"][-1]["detail"])
        self.assertEqual(self.journal()["operations"][-1]["outcome"], journal.FAILED)

    def test_cli_error_but_app_present_is_verified_by_readback(self):
        r = self.install(FakeTV(install_reports_error_but_installed=True))
        self.assertEqual(r.outcome, journal.APPLIED)
        self.assertIn("CLI reported", self.journal()["operations"][-1]["detail"])

    def test_successful_install_then_failed_launch(self):
        tv = FakeTV(launch_fails=True)
        r = self.install(tv)
        self.assertEqual(r.outcome, journal.APPLIED)
        self.assertFalse(r.stages["launched"])
        self.assertNotIn("ready", r.stages)
        self.assertEqual(r.exit_code, 1)
        self.assertFalse(journal.launcher_ready(self.journal()))

    def test_launch_acknowledged_but_not_running_or_ready(self):
        tv = FakeTV(launch_ack_without_run=True)
        r = self.install(tv, confirm=lambda q: False, foreground=lambda: "com.webos.app.home")
        self.assertTrue(r.stages["launched"])
        self.assertFalse(r.stages["running"])
        self.assertFalse(r.stages["foreground"])
        self.assertEqual(r.stages["ready"], "user-denied")
        self.assertEqual(r.exit_code, 1)
        self.assertFalse(journal.launcher_ready(self.journal()))

    def test_foreground_is_asked_again_while_the_window_comes_up(self):
        answers = iter(["", "", self.app])   # webOS 22 reports an empty foreground app just after a launch
        with mock.patch.object(lifecycle.time, "sleep") as slept:
            r = self.install(FakeTV(), foreground=lambda: next(answers))
        self.assertTrue(r.stages["foreground"])
        self.assertEqual(slept.call_count, 2)
        with mock.patch.object(lifecycle.time, "sleep"):
            r = lifecycle.install(DEV, FakeTV(), self.ipk, self.profiles, adopt=True, foreground=lambda: "com.webos.app.home")
        self.assertFalse(r.stages.get("foreground", False))

    def test_no_person_to_ask_leaves_readiness_unconfirmed(self):
        r = self.install(FakeTV(), confirm=None)
        self.assertEqual(r.stages["ready"], "unconfirmed")
        self.assertFalse(journal.launcher_ready(self.journal()))

    def test_link_lost_after_install_is_unknown_until_reconciled(self):
        tv = FakeTV(link_lost_after_install=True)
        r = self.install(tv)
        self.assertEqual(r.outcome, journal.UNKNOWN)
        self.assertEqual(r.exit_code, 2)
        self.assertEqual(self.journal()["owned"], {})
        self.assertEqual(self.journal()["operations"][-1]["outcome"], journal.UNKNOWN)
        tv.faults.clear()
        _, _, status = lifecycle.status(DEV, tv)
        self.assertIn("reconciled", " ".join(status.messages))
        j = self.journal()
        self.assertEqual(j["operations"][-1]["outcome"], journal.APPLIED)
        self.assertIn(self.app, j["owned"])

    def test_link_lost_before_install_reconciles_to_failed_then_retry_installs(self):
        tv = FakeTV(link_lost_before_install=True)
        self.assertEqual(self.install(tv).outcome, journal.UNKNOWN)
        tv.faults.clear()
        r = self.install(tv)
        ops = self.journal()["operations"]
        self.assertEqual([o["outcome"] for o in ops], [journal.FAILED, journal.APPLIED])
        self.assertEqual(r.outcome, journal.APPLIED)

    def test_unreadable_result_after_install_is_unknown(self):
        r = self.install(FakeTV(readback_fails=True))
        self.assertEqual(r.outcome, journal.UNKNOWN)
        self.assertEqual(self.journal()["operations"][-1]["outcome"], journal.UNKNOWN)

    def test_interrupted_install_is_reconciled_before_anything_else(self):
        tv = FakeTV()
        self.install(tv)
        data = self.journal()
        # A crash after the intent was written and before the outcome: the op stays pending.
        journal.begin(DEV, data, "install", app_id=self.app, version="0.0.9", sha256="x")
        with self.assertRaises(Refused) as ctx:
            self.install(tv)
        self.assertIn("unknown outcome", str(ctx.exception))
        self.assertEqual(len(tv.mutations()), 2, "nothing new may be sent while an outcome is unknown")

    def test_repeated_install_of_the_same_package_does_not_reinstall(self):
        tv = FakeTV()
        self.install(tv)
        before = [c for c in tv.calls if c.startswith("install:")]
        r = self.install(tv)
        self.assertEqual(r.outcome, journal.APPLIED)
        self.assertEqual([c for c in tv.calls if c.startswith("install:")], before)

    def test_app_installed_by_something_else_is_refused_then_adopted_and_kept_on_restore(self):
        tv = FakeTV()
        tv.installed_apps[self.app] = "0.0.1"
        with self.assertRaises(Refused):
            self.install(tv)
        self.assertEqual(tv.mutations(), [])
        self.assertEqual(self.install(tv, adopt=True).outcome, journal.APPLIED)
        r = lifecycle.restore(DEV, tv)
        self.assertEqual(r.outcome, journal.INCOMPLETE)
        self.assertIn(self.app, tv.installed_apps, "restore must not remove what it did not install")

    def test_concurrent_change_on_the_tv_is_detected(self):
        tv = FakeTV()
        self.install(tv)
        tv.installed_apps[self.app] = "9.9.9"    # updated by someone else since
        with self.assertRaises(Refused):
            self.install(tv)
        with self.assertRaises(Refused):
            lifecycle.restore(DEV, tv)
        self.assertEqual(tv.installed_apps[self.app], "9.9.9")

    def test_second_run_while_one_holds_the_lock_is_refused(self):
        tv = FakeTV()
        with store.DeviceLock(DEV):
            with self.assertRaises(Refused) as ctx:
                self.install(tv)
        self.assertIn("another cytv-webos run", str(ctx.exception))
        self.assertEqual(tv.mutations(), [])

    def test_missing_cli_refuses_before_any_call(self):
        tv = FakeTV()
        tv.missing = ["ares-install"]
        with self.assertRaises(Refused):
            self.install(tv)
        self.assertEqual(tv.calls, [])

    def test_unsupported_sdk_refuses(self):
        tv = FakeTV()
        tv.facts["sdkVersion"] = "2.0.0"
        with self.assertRaises(Refused):
            self.install(tv)
        self.assertEqual(tv.mutations(), [])

    def test_pairing_revoked_is_refused_and_nothing_sent(self):
        tv = FakeTV(pairing_refused=True)
        with self.assertRaises(PairingError):
            self.install(tv)
        self.assertEqual(tv.mutations(), [])

    def test_local_disk_full_refuses_before_the_tv_is_touched(self):
        tv = FakeTV()
        with mock.patch.object(store, "write_json", side_effect=OSError(28, "No space left on device")):
            with self.assertRaises(Refused) as ctx:
                self.install(tv)
        self.assertIn("Nothing was sent", str(ctx.exception))
        self.assertEqual(tv.mutations(), [])

    def test_corrupt_journal_is_refused_and_left_untouched(self):
        path = journal.path_for(DEV)
        path.parent.mkdir(parents=True)
        path.write_text("{not json")
        with self.assertRaises(Refused):
            self.install(FakeTV())
        self.assertEqual(path.read_text(), "{not json")

    def test_journal_from_another_version_is_refused(self):
        path = journal.path_for(DEV)
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"version": 99}))
        with self.assertRaises(Refused) as ctx:
            lifecycle.restore(DEV, FakeTV())
        self.assertIn("not the supported version", str(ctx.exception))

    def test_a_package_with_another_app_id_is_refused(self):
        tv = FakeTV()
        self.install(tv)
        other, _ = variant_ipk(app_id="com.example.other")
        with self.assertRaises(Refused):
            lifecycle.install(DEV, tv, other, self.profiles, expect_id=self.app)
        with self.assertRaises(Refused) as ctx:          # even without expect_id: not the owned app
            lifecycle.install(DEV, tv, other, self.profiles)
        self.assertIn("manages", str(ctx.exception))
        self.assertEqual(list(self.journal()["owned"]), [self.app])
        self.assertNotIn("com.example.other", tv.installed_apps)

    def test_update_that_never_landed_reconciles_to_failed_and_unblocks(self):
        tv = FakeTV()
        self.install(tv)
        newer, info = variant_ipk(version="0.2.0")
        tv.faults["link_lost_before_install"] = True
        r = lifecycle.install(DEV, tv, newer, self.profiles, confirm=yes)
        self.assertEqual(r.outcome, journal.UNKNOWN)
        self.assertFalse(journal.launcher_ready(self.journal()), "nothing is ready while an outcome is open")
        tv.faults.clear()
        lifecycle.status(DEV, tv)
        ops = self.journal()["operations"]
        self.assertEqual(ops[-1]["outcome"], journal.FAILED)
        self.assertIn("still has the version from before (0.1.0)", ops[-1]["detail"])
        self.assertEqual(lifecycle.install(DEV, tv, newer, self.profiles, confirm=yes).outcome, journal.APPLIED)
        self.assertEqual(tv.installed_apps[self.app], "0.2.0")
        self.assertEqual(lifecycle.restore(DEV, tv).outcome, journal.RESTORED)

    def test_a_new_install_clears_readiness_until_confirmed_again(self):
        tv = FakeTV()
        self.install(tv)
        self.assertTrue(journal.launcher_ready(self.journal()))
        newer, _ = variant_ipk(version="0.3.0")
        lifecycle.install(DEV, tv, newer, self.profiles, confirm=None)
        self.assertFalse(journal.launcher_ready(self.journal()))

    def test_malformed_package_is_refused_before_the_tv_is_asked(self):
        bad = Path(self.root) / "bad.ipk"
        data = self.ipk.read_bytes()
        bad.write_bytes(data[:len(data) // 2])
        tv = FakeTV()
        with self.assertRaises(Refused):
            lifecycle.install(DEV, tv, bad, self.profiles)
        self.assertEqual(tv.calls, [])

    def test_records_are_private_to_the_user(self):
        self.install(FakeTV())
        mode = os.stat(journal.path_for(DEV)).st_mode & 0o777
        self.assertEqual(mode, 0o600)


class RestoreTest(Base):
    def test_restore_removes_and_verifies(self):
        tv = FakeTV()
        self.install(tv)
        r = lifecycle.restore(DEV, tv)
        self.assertEqual(r.outcome, journal.RESTORED)
        self.assertNotIn(self.app, tv.installed_apps)
        self.assertEqual(self.journal()["owned"], {})
        self.assertEqual(r.exit_code, 0)

    def test_failed_removal_is_never_reported_as_restored(self):
        tv = FakeTV()
        self.install(tv)
        tv.faults["remove_fails"] = True
        r = lifecycle.restore(DEV, tv)
        self.assertEqual(r.outcome, journal.INCOMPLETE)
        self.assertEqual(r.exit_code, 2)
        self.assertIn(self.app, self.journal()["owned"])
        self.assertEqual(self.journal()["operations"][-1]["outcome"], journal.INCOMPLETE)

    def test_link_lost_during_removal_is_unknown_then_reconciled(self):
        tv = FakeTV()
        self.install(tv)
        tv.faults["link_lost_after_remove"] = True
        self.assertEqual(lifecycle.restore(DEV, tv).outcome, journal.UNKNOWN)
        self.assertEqual(self.journal()["operations"][-1]["outcome"], journal.UNKNOWN)
        tv.faults.clear()
        lifecycle.status(DEV, tv)
        self.assertEqual(self.journal()["operations"][-1]["outcome"], journal.RESTORED)

    def test_without_a_journal_nothing_is_invented(self):
        tv = FakeTV()
        tv.installed_apps[self.app] = "0.1.0"
        with self.assertRaises(Refused) as ctx:
            lifecycle.restore(DEV, tv)
        self.assertIn("nothing will be removed", str(ctx.exception))
        self.assertEqual(tv.mutations(), [])

    def test_refused_restore_still_stops_home_routing(self):
        tv = FakeTV()
        self.install(tv)
        integration.transition(DEV, "activate", "test", backend="external-watcher")
        tv.faults["readback_fails"] = True
        data = self.journal()
        journal.begin(DEV, data, "install", app_id=self.app, version="9.0.0", sha256="x")
        tv.calls.append("install:x")      # so the fake's readback fault applies
        with self.assertRaises(Refused):
            lifecycle.restore(DEV, tv)
        self.assertEqual(integration.load(DEV)["state"], "stopped")

    def test_restore_stops_home_integration_first(self):
        tv = FakeTV()
        self.install(tv)
        integration.transition(DEV, "activate", "test", backend="external-watcher")
        r = lifecycle.restore(DEV, tv)
        self.assertEqual(integration.load(DEV)["state"], "stopped")
        self.assertIn("Home integration stopped", " ".join(r.messages))

    def test_restore_only_touches_its_own_app(self):
        tv = FakeTV()
        tv.installed_apps["com.other.app"] = "1.0.0"
        self.install(tv)
        lifecycle.restore(DEV, tv)
        self.assertEqual(tv.installed_apps, {"com.other.app": "1.0.0"})
        self.assertEqual([c for c in tv.mutations() if c.startswith("remove:")], [f"remove:{self.app}"])


if __name__ == "__main__":
    unittest.main()
