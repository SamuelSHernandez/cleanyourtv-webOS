"""The IPK builder and verifier, profiles, capability report and inventory baking."""
import copy
import gzip
import io
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest import mock

from faketv import FakeTV, StateDir, launcher_ipk

from cytv_webos import build, capabilities, inventory, ipk, profiles, ssap
from cytv_webos.errors import Refused

ROOT = Path(__file__).resolve().parents[1]


def data_names(path):
    members = ipk.read_members(Path(path).read_bytes())
    tar = tarfile.open(fileobj=io.BytesIO(gzip.decompress(members[2][1])))
    return tar.getnames()


def repack(path, mutate_control=None, extra=None):
    """A copy of an IPK with a changed control file or an extra data file, for refusal tests."""
    members = dict(ipk.read_members(Path(path).read_bytes()))
    if mutate_control:
        tar = tarfile.open(fileobj=io.BytesIO(gzip.decompress(members["control.tar.gz"])))
        control = mutate_control(tar.extractfile("./control").read().decode()).encode()
        members["control.tar.gz"] = ipk._tar_gz([("./", None), ("./control", control)], 0)
    if extra:
        tar = tarfile.open(fileobj=io.BytesIO(gzip.decompress(members["data.tar.gz"])))
        entries = [(m.name, tar.extractfile(m).read() if m.isfile() else None) for m in tar.getmembers()]
        entries.append(extra)
        members["data.tar.gz"] = ipk._tar_gz(entries, 0)
    out = Path(tempfile.mkdtemp()) / "x.ipk"
    out.write_bytes(ipk._ar([(n, members[n]) for n in ("debian-binary", "control.tar.gz", "data.tar.gz")], 0))
    return out


class PackageTest(unittest.TestCase):
    def test_build_is_repeatable(self):
        a = Path(tempfile.mkdtemp())
        b = Path(tempfile.mkdtemp())
        pa, da, _ = build.build(None, a)
        pb, db, _ = build.build(None, b)
        self.assertEqual(da, db)
        self.assertEqual(pa.read_bytes(), pb.read_bytes())

    def test_package_layout_and_no_preview_code(self):
        path, info = launcher_ipk()
        names = data_names(path)
        app = f"./usr/palm/applications/{info['id']}/"
        for f in ("index.html", "appinfo.json", "js/app.js", "js/inventory.js", "icon.png", "largeIcon.png"):
            self.assertIn(app + f, names)
        self.assertIn(f"./usr/palm/packages/{info['id']}/packageinfo.json", names)
        self.assertFalse([n for n in names if "preview" in n])

    def test_native_binary_is_refused(self):
        path, info = launcher_ipk()
        bad = repack(path, extra=(f"./usr/palm/applications/{info['id']}/helper", b"\x7fELF\x01\x01"))
        with self.assertRaises(Refused) as ctx:
            build.verify(bad)
        self.assertIn("native binary", str(ctx.exception))

    def test_architecture_mismatch_is_refused(self):
        path, _ = launcher_ipk()
        bad = repack(path, mutate_control=lambda c: c.replace("Architecture: all", "Architecture: arm"))
        with self.assertRaises(Refused) as ctx:
            build.verify(bad)
        self.assertIn("architecture", str(ctx.exception))

    def test_preview_adapter_in_a_package_is_refused(self):
        path, info = launcher_ipk()
        bad = repack(path, extra=(f"./usr/palm/applications/{info['id']}/js/preview-adapter.js", b"x"))
        with self.assertRaises(Refused):
            build.verify(bad)

    def test_wrong_expected_version_is_refused(self):
        path, info = launcher_ipk()
        with self.assertRaises(Refused):
            build.verify(path, expect_version="9.9.9")

    def test_not_an_ipk(self):
        p = Path(tempfile.mkdtemp()) / "x.ipk"
        p.write_bytes(b"PK\x03\x04")
        with self.assertRaises(Refused):
            build.verify(p)

    def test_source_with_unexpected_file_types_is_refused(self):
        d = Path(tempfile.mkdtemp()) / "app"
        shutil.copytree(build.LAUNCHER, d)
        (d / "tool.sh").write_text("echo hi")
        with self.assertRaises(Refused):
            ipk.app_files(d)

    def test_appinfo_validation(self):
        d = Path(tempfile.mkdtemp())
        for bad in ({"id": "Bad", "version": "1.0.0", "type": "web", "main": "index.html"},
                    {"id": "a.b.c", "version": "1.0", "type": "web", "main": "index.html"},
                    {"id": "a.b.c", "version": "1.0.0", "type": "native", "main": "index.html"}):
            (d / "appinfo.json").write_text(json.dumps(bad))
            with self.assertRaises(Refused):
                ipk.read_appinfo(d)

    def test_shipped_appinfo_asks_only_for_launching(self):
        info = json.loads((build.LAUNCHER / "appinfo.json").read_text())
        self.assertEqual(info["requiredACG"], ["application.launcher"])
        self.assertTrue(info["disableBackHistoryAPI"])
        self.assertNotEqual(info["id"], "com.gathin.tvhome", "must not collide with other projects' app id")
        self.assertFalse(info["id"].startswith("com.cleanyourtv."))


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.p = profiles.load_all()[0]

    def test_shipped_profiles_validate(self):
        self.assertTrue(profiles.load_all())

    def test_selection_by_sdk(self):
        all_ = profiles.load_all()
        self.assertEqual(profiles.select(all_, "8.2.0")["id"], "webos-devmode-generic")
        self.assertIsNone(profiles.select(all_, "2.1"))
        self.assertIsNone(profiles.select(all_, None))
        self.assertIsNone(profiles.select(all_, "garbage"))

    def test_malformed_profiles_are_refused(self):
        def broken(change):
            p = copy.deepcopy(self.p)
            change(p)
            with self.assertRaises(Refused):
                profiles.validate(p)
        broken(lambda p: p.update(schema=2))
        broken(lambda p: p.update(extra=1))
        broken(lambda p: p["backends"]["manual"].update(evidence="works great"))
        broken(lambda p: p["backends"].update(root={"evidence": "automated-tests-only", "requires": []}))
        broken(lambda p: p["home_app_ids"].append("bad id"))
        broken(lambda p: p["evidence"].append({"model": "C3", "firmware": "1.2", "app_version": "0.1.0",
                                               "backend": "manual", "level": "certified", "date": "2026-10-26"}))
        broken(lambda p: p["evidence"].append({"model": "C3", "firmware": "1.2", "app_version": "0.1.0",
                                               "backend": "manual", "level": "community-reported",
                                               "date": "2026-10-26", "serial": "123"}))

    def test_no_hardware_claims_without_evidence(self):
        for p in profiles.load_all():
            levels = {e["level"] for e in p["evidence"]}
            for name, spec in p["backends"].items():
                if spec["evidence"] not in ("automated-tests-only", "known-incompatible"):
                    self.assertIn(spec["evidence"], levels, f"{p['id']}.{name} claims evidence it does not list")


class CapabilityTest(unittest.TestCase):
    def setUp(self):
        self.s = StateDir()
        self.s.__enter__()

    def tearDown(self):
        self.s.__exit__(None, None, None)

    def test_report_keeps_private_identifiers_out(self):
        report = capabilities.collect(FakeTV(), profiles.load_all(), None, "x.y.z", "tv")
        text = json.dumps(report) + capabilities.render(report)
        self.assertNotIn("SERIAL-SHOULD-NOT-LEAK", text)
        self.assertNotIn("aa:bb:cc", text)
        self.assertEqual(set(report["tv"]), {"modelName", "sdkVersion", "firmwareVersion"})

    def test_conflicts_and_eligibility_are_explained(self):
        tv = FakeTV()
        tv.installed_apps["com.local.nativehome"] = "1.0.0"
        report = capabilities.collect(tv, profiles.load_all(), None, "x.y.z", "tv")
        self.assertEqual([c["id"] for c in report["conflicts"]], ["com.local.nativehome"])
        self.assertTrue(report["backends"]["manual"]["eligible"])
        reasons = " ".join(report["backends"]["external-watcher"]["reasons"])
        self.assertIn("SSAP not paired", reasons)
        self.assertIn("readiness not confirmed", reasons)
        self.assertIn("com.local.nativehome", reasons)
        self.assertIn("conflict detection is incomplete", " ".join(report["problems"]))

    def test_unreachable_tv_is_not_eligible_for_anything(self):
        report = capabilities.collect(FakeTV(unreachable=True), profiles.load_all(), None, "x.y.z", "tv")
        self.assertIsNone(report["profile"])
        self.assertEqual(report["backends"], {})
        self.assertTrue(report["problems"])

    def test_missing_cli_is_reported_not_crashed(self):
        tv = FakeTV()
        tv.missing = ["ares-install", "ares-launch"]
        report = capabilities.collect(tv, profiles.load_all(), None, "x.y.z", "tv")
        self.assertIn("missing", report["problems"][0])
        self.assertEqual(tv.calls, [])


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


class FakeSession:
    def request(self, uri, payload=None):
        if uri.endswith("listLaunchPoints"):
            return {"returnValue": True, "launchPoints": [
                {"id": "netflix", "title": "Netflix", "icon": "http://192.168.1.50:3000/resources/a/icon.png"},
                {"id": "evil.app", "title": "</script><script>alert(1)</script>",
                 "icon": "file:///etc/passwd"},
                {"id": "hidden.app", "title": "Hidden", "hidden": True}]}
        if uri.endswith("getExternalInputList"):
            return {"returnValue": True, "devices": [
                {"id": "HDMI_1", "label": "PlayStation", "appId": "com.webos.app.hdmi1"},
                {"id": "HDMI_2", "label": "bad\u0007label", "appId": "com.webos.app.hdmi2"},
                {"id": "X", "label": "No app"}]}
        if uri.endswith("listApps"):
            return {"returnValue": True, "apps": [{"id": "netflix"}, {"id": "com.palm.app.settings"},
                                                  {"id": "com.webos.app.inputmgr"}]}
        raise AssertionError(uri)


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.s = StateDir()
        self.s.__enter__()

    def tearDown(self):
        self.s.__exit__(None, None, None)

    def test_icon_fetch_refuses_other_hosts_ports_and_schemes(self):
        host = "192.168.1.50"
        with mock.patch("http.client.HTTPConnection") as conn:
            for url in ("file:///etc/passwd", "http://evil.example:3000/i.png", "http://192.168.1.50:8080/i.png",
                        "ftp://192.168.1.50:3000/i.png", "http://192.168.1.50/i.png", "not a url"):
                self.assertIsNone(inventory.fetch_icon(url, host, "ab"))
            conn.assert_not_called()

    def test_sync_resolves_shortcuts_skips_hidden_and_bad_icons(self):
        fetched = []

        def fetch(url, host, pin):
            fetched.append(url)
            return PNG if url.startswith("http://192.168.1.50:3000/") else None
        record, missing = inventory.sync("tv", "192.168.1.50", FakeSession(), profiles.load_all()[0], fetch=fetch)
        self.assertEqual([a["id"] for a in record["apps"]], ["netflix", "evil.app"])
        self.assertEqual(record["shortcuts"], {"inputs": "com.webos.app.inputmgr",
                                               "settings": "com.palm.app.settings", "livetv": None})
        self.assertEqual(missing, 1)
        self.assertEqual(record["inputs"], [{"app": "com.webos.app.hdmi1", "label": "PlayStation"}])
        self.assertTrue(record["apps"][0]["art"].endswith(".png"))
        self.assertEqual(inventory.load("tv"), record)

    def test_baked_script_cannot_break_out_of_its_script_tag(self):
        record, _ = inventory.sync("tv", "192.168.1.50", FakeSession(), profiles.load_all()[0],
                                   fetch=lambda *a: None)
        text = inventory.baked_script(record, "x.y.z", "test")
        self.assertNotIn("</script>", text)
        self.assertNotIn("<", text.split("\n", 1)[1])

    def test_tampered_inventory_is_refused(self):
        record, _ = inventory.sync("tv", "192.168.1.50", FakeSession(), profiles.load_all()[0],
                                   fetch=lambda *a: None)
        record["apps"][0]["art"] = "../../etc/passwd"
        with self.assertRaises(Refused):
            inventory.validate(record)

    def test_build_with_a_synced_tv_bakes_its_apps(self):
        inventory.sync("tv", "192.168.1.50", FakeSession(), profiles.load_all()[0], fetch=lambda *a: PNG)
        out = Path(tempfile.mkdtemp())
        path, _, info = build.build("tv", out)
        names = data_names(path)
        art = [n for n in names if "/art/" in n]
        self.assertEqual(len(art), 2)
        stage_js = (out / "stage" / info["id"] / "js" / "inventory.js").read_text()
        self.assertIn('"netflix"', stage_js)


if __name__ == "__main__":
    unittest.main()
