"""Add-ons: the card rules (upstream spec 1), the build, the repo's rules for add-on folders, and the flow."""
import gzip
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest

from faketv import FakeTV, StateDir

from cytv_webos import addons, build, inventory, ipk, journal, lifecycle, profiles
from cytv_webos.errors import Refused

ROOT = Path(__file__).resolve().parents[1]
DEV = "tv"


def names_in(path):
    members = dict(ipk.read_members(Path(path).read_bytes()))
    return tarfile.open(fileobj=io.BytesIO(gzip.decompress(members["data.tar.gz"]))).getnames()


class CardRulesTest(unittest.TestCase):
    def ok(self, **card):
        return addons.validate_card(dict({"spec": 1}, **card), "a.b.c")

    def test_good_cards(self):
        self.assertEqual(self.ok(label="Retro", caption="NES games", accent="#E8A33D")["label"], "Retro")
        self.assertEqual(self.ok(label="Night Clock")["caption"], "")

    def test_spec_1_rules_are_upstream_rules(self):
        for card in ({"label": "x" * 25}, {"label": " Lead"}, {"label": "<b>"}, {"label": "!!!"}, {"label": "Live TV"},
                     {"label": "live-tv"}, {"label": "HDMI 3"}, {"label": "AV"}, {"label": "Official Apps"},
                     {"label": "Retro", "caption": "verified build"}, {"label": "Retro", "accent": "red"},
                     {"label": "Retro", "caption": "y" * 33}, {"label": "Retro", "extra": 1}, {"label": "Clock"},
                     {"label": "CleanYourTV"}):
            with self.assertRaises(Refused, msg=card):
                self.ok(**card)
        with self.assertRaises(Refused):
            addons.validate_card({"spec": 2, "label": "Retro"}, "a.b.c")

    def test_a_label_another_app_has_is_refused_at_approval(self):
        with StateDir():
            card = self.ok(label="Spotify")
            with self.assertRaises(Refused):
                addons.decide(DEV, card, "show", ["Spotify", "YouTube"], "x")
            addons.decide(DEV, card, "hide", ["Spotify"], "x")   # hiding is always allowed
            self.assertEqual(addons.shown_cards(DEV), [])

    def test_a_new_decision_replaces_the_old_one_for_that_app(self):
        with StateDir():
            addons.decide(DEV, self.ok(label="Retro"), "show", [], "x")
            addons.decide(DEV, self.ok(label="Arcade"), "show", [], "y")
            self.assertEqual([c["label"] for c in addons.shown_cards(DEV)], ["Arcade"])


class AddonFoldersTest(unittest.TestCase):
    def folders(self):
        return sorted(p for p in addons.ADDONS.iterdir() if p.is_dir())

    def test_every_addon_follows_the_repo_rules(self):
        self.assertTrue(self.folders())
        launcher_id = build.launcher_info()["id"]
        for folder in self.folders():
            a = addons.load(folder)
            self.assertNotEqual(a["appinfo"]["id"], launcher_id)
            self.assertTrue((folder / "screenshot.jpg").is_file(), f"{folder.name}: screenshot.jpg from a real TV is required")
            self.assertTrue((folder / "screenshot.jpg").read_bytes().startswith(b"\xff\xd8\xff"))
            self.assertLessEqual((folder / "screenshot.jpg").stat().st_size, 300 * 1024)
            readme = (folder / "README.md").read_text()
            self.assertIn("## Permissions", readme)
            self.assertIn("Tested on:", readme)
            html = (folder / "app" / "index.html").read_text()
            self.assertIn("connect-src 'none'", html, f"{folder.name}: an add-on with network use says so and is reviewed apart")
            self.assertIn(folder.name, (addons.ADDONS / "README.md").read_text())

    def test_build_draws_missing_icons_and_never_packs_the_screenshot(self):
        path, _, info = addons.build(addons.ADDONS / "night-clock", Path(tempfile.mkdtemp()))
        names = names_in(path)
        app = f"./usr/palm/applications/{info['id']}/"
        self.assertIn(app + "icon.png", names)
        self.assertIn(app + "largeIcon.png", names)
        self.assertFalse([n for n in names if "screenshot" in n or "card.json" in n or "README" in n])

    def test_an_addon_cannot_take_the_launchers_id(self):
        d = Path(tempfile.mkdtemp()) / "evil"
        shutil.copytree(addons.ADDONS / "night-clock", d)
        info = json.loads((d / "app" / "appinfo.json").read_text())
        info["id"] = build.launcher_info()["id"]
        (d / "app" / "appinfo.json").write_text(json.dumps(info))
        with self.assertRaises(Refused):
            addons.build(d, Path(tempfile.mkdtemp()))

    def test_readme_without_permissions_is_refused(self):
        d = Path(tempfile.mkdtemp()) / "noperm"
        shutil.copytree(addons.ADDONS / "night-clock", d)
        (d / "README.md").write_text("# x\n")
        with self.assertRaises(Refused):
            addons.load(d)


class AddonFlowTest(unittest.TestCase):
    def setUp(self):
        self.s = StateDir()
        self.s.__enter__()

    def tearDown(self):
        self.s.__exit__(None, None, None)

    def test_install_approve_bake_and_remove_only_the_addon(self):
        tv = FakeTV()
        out = Path(tempfile.mkdtemp())
        launcher, _, linfo = build.build(None, out)
        from unittest import mock
        with mock.patch.object(lifecycle.time, "sleep"):
            lifecycle.install(DEV, tv, launcher, profiles.load_all(), confirm=lambda q: True, expect_id=linfo["id"])
        path, digest, info = addons.build(addons.ADDONS / "night-clock", out)
        r = lifecycle.install(DEV, tv, path, profiles.load_all(), expect_id=info["id"], role="addon")
        self.assertEqual(r.outcome, journal.APPLIED)
        self.assertNotIn("launched", r.stages, "an add-on is installed, not launched")
        data = journal.load(DEV)
        self.assertEqual(data["owned"][info["id"]]["role"], "addon")
        self.assertTrue(journal.launcher_ready(data), "installing an add-on leaves the launcher's readiness alone")
        with self.assertRaises(Refused):   # an add-on install may not replace the launcher
            lifecycle.install(DEV, tv, launcher, profiles.load_all(), expect_id=linfo["id"], role="addon")
        card = addons.load(addons.ADDONS / "night-clock")["card"]
        addons.decide(DEV, card, "show", ["Spotify"], digest)
        inventory.store.write_json(inventory.inv_dir(DEV) / "inventory.json",
                                   {"version": 1, "synced": "x", "apps": [{"id": info["id"], "title": "Night Clock", "art": None}],
                                    "inputs": [], "shortcuts": {"inputs": None, "settings": None, "livetv": None}})
        baked, _, _ = build.build(DEV, out)
        stage = (out / "stage" / linfo["id"] / "js" / "inventory.js").read_text()
        self.assertIn('"label": "Night Clock"', stage)
        r = lifecycle.restore(DEV, tv, only=info["id"])
        self.assertEqual(r.outcome, journal.RESTORED)
        self.assertIn(linfo["id"], tv.installed_apps, "removing the add-on leaves the launcher")
        self.assertNotIn(info["id"], tv.installed_apps)
        with self.assertRaises(Refused):
            lifecycle.restore(DEV, tv, only="com.not.ours")


if __name__ == "__main__":
    unittest.main()
