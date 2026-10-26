"""The cytv-webos command end to end, with fake ares-* executables standing in for LG's CLI and TV."""
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from faketv import launcher_ipk

ROOT = Path(__file__).resolve().parents[1]

FAKE_ARES = r'''#!PYTHON
import gzip, io, json, os, sys, tarfile
tool = os.path.basename(sys.argv[0])
args = sys.argv[1:]
path = os.environ["FAKE_ARES_STATE"]
state = json.load(open(path))
def save():
    json.dump(state, open(path, "w"))
state["log"].append([tool] + args)
save()
if "--version" in args:
    print("Version: 3.2.1"); sys.exit(0)
if state.get("offline"):
    print("Error: connect ETIMEDOUT 192.168.1.50:9922", file=sys.stderr); sys.exit(1)
if tool == "ares-device":
    print("modelName : OLED55C3\nsdkVersion : 8.2.0\nfirmwareVersion : 33.21.71\nserial : SECRET"); sys.exit(0)
if tool == "ares-install" and "--listfull" in args:
    for i, v in state["apps"].items():
        print(f"id : {i}\nversion : {v}\n")
    sys.exit(0)
if tool == "ares-install" and "--remove" in args:
    if state.get("remove_fails"):
        print("Error: FAILED_REMOVE", file=sys.stderr); sys.exit(1)
    state["apps"].pop(args[-1], None); save(); sys.exit(0)
if tool == "ares-install":
    if state.get("install_fails"):
        print("Error: FAILED_IPKG_INSTALL: not enough space", file=sys.stderr); sys.exit(1)
    data = open(args[-1], "rb").read()
    pos = 8; members = {}
    while pos < len(data):
        h = data[pos:pos + 60]; name = h[:16].decode().strip().rstrip("/"); size = int(h[48:58])
        members[name] = data[pos + 60:pos + 60 + size]; pos += 60 + size + size % 2
    tar = tarfile.open(fileobj=io.BytesIO(gzip.decompress(members["data.tar.gz"])))
    for m in tar.getmembers():
        if m.name.endswith("/appinfo.json"):
            info = json.load(tar.extractfile(m))
    state["apps"][info["id"]] = info["version"]; save()
    print("Success"); sys.exit(0)
if tool == "ares-launch" and "--running" in args:
    print("\n".join(state["running"])); sys.exit(0)
if tool == "ares-launch" and "--close" in args:
    sys.exit(0)
if tool == "ares-launch":
    if args[-1] not in state["apps"]:
        print("Error: app not installed", file=sys.stderr); sys.exit(1)
    state["running"].append(args[-1]); save(); print("Launched application " + args[-1]); sys.exit(0)
sys.exit(2)
'''


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.bin = base / "bin"
        self.bin.mkdir()
        script = FAKE_ARES.replace("#!PYTHON", "#!" + sys.executable)
        for tool in ("ares-install", "ares-launch", "ares-device"):
            p = self.bin / tool
            p.write_text(script)
            p.chmod(p.stat().st_mode | stat.S_IXUSR)
        self.state_file = base / "tv.json"
        self.write_state(apps={}, running=[], log=[])
        self.env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                        FAKE_ARES_STATE=str(self.state_file), CYTV_WEBOS_HOME=str(base / "home"))
        self.ipk, self.info = launcher_ipk()

    def tearDown(self):
        self.tmp.cleanup()

    def write_state(self, **state):
        self.state_file.write_text(json.dumps(state))

    def tv(self):
        return json.loads(self.state_file.read_text())

    def cli(self, *args):
        p = subprocess.run([str(ROOT / "cytv-webos"), *args], env=self.env, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        return p.returncode, p.stdout + p.stderr

    def test_install_status_restore(self):
        self.assertEqual(self.cli("setup", "--device", "tv", "--host", "192.168.1.50")[0], 0)
        code, out = self.cli("install", "--device", "tv", "--ipk", str(self.ipk))
        self.assertEqual(code, 0, out)
        self.assertIn("installed   yes", out)
        self.assertIn("ready       unconfirmed", out, "no terminal: readiness is not assumed")
        self.assertIn("home        not changed by install", out)
        self.assertNotIn("SECRET", out)
        self.assertEqual(self.tv()["apps"], {self.info["id"]: self.info["version"]})
        code, out = self.cli("home", "enable", "--device", "tv")
        self.assertEqual(code, 1)
        self.assertIn("readiness is not confirmed", out)
        code, out = self.cli("status", "--device", "tv")
        self.assertEqual(code, 0, out)
        self.assertIn(f"owned:   {self.info['id']}", out)
        code, out = self.cli("restore", "--device", "tv")
        self.assertEqual(code, 0, out)
        self.assertIn("verified absent", out)
        self.assertEqual(self.tv()["apps"], {})

    def test_failed_install_exits_nonzero_and_launches_nothing(self):
        self.cli("setup", "--device", "tv", "--host", "192.168.1.50")
        state = self.tv()
        state["install_fails"] = True
        self.write_state(**state)
        code, out = self.cli("install", "--device", "tv", "--ipk", str(self.ipk))
        self.assertEqual(code, 1)
        self.assertIn("not enough space", out)
        self.assertFalse([c for c in self.tv()["log"] if c[0] == "ares-launch"])

    def test_failed_restore_exits_2_and_says_incomplete(self):
        self.cli("setup", "--device", "tv", "--host", "192.168.1.50")
        self.cli("install", "--device", "tv", "--ipk", str(self.ipk))
        state = self.tv()
        state["remove_fails"] = True
        self.write_state(**state)
        code, out = self.cli("restore", "--device", "tv")
        self.assertEqual(code, 2)
        self.assertIn("recovery_incomplete", out)
        self.assertNotIn("restored_verified", out)

    def test_offline_tv_is_refused_before_any_change(self):
        self.cli("setup", "--device", "tv", "--host", "192.168.1.50")
        state = self.tv()
        state["offline"] = True
        self.write_state(**state)
        code, out = self.cli("install", "--device", "tv", "--ipk", str(self.ipk))
        self.assertEqual(code, 1)
        self.assertIn("Nothing was changed", out)
        self.assertFalse([c for c in self.tv()["log"] if c[0] == "ares-install" and c[-1].endswith(".ipk")])

    def test_home_stop_and_resume_are_explicit(self):
        self.cli("setup", "--device", "tv", "--host", "192.168.1.50")
        self.assertEqual(self.cli("home", "stop", "--device", "tv")[0], 0)
        code, out = self.cli("home", "status", "--device", "tv")
        self.assertIn("stopped", out)
        code, out = self.cli("home", "deactivate", "--device", "tv")
        self.assertEqual(code, 1, "a stopped integration only leaves through resume")
        self.assertEqual(self.cli("home", "resume", "--device", "tv")[0], 0)
        self.assertIn("inactive", self.cli("home", "status", "--device", "tv")[1])

    def test_bad_input_is_refused_with_one_line(self):
        code, out = self.cli("setup", "--device", "tv;rm", "--host", "192.168.1.50")
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", out)
        code, out = self.cli("install", "--device", "nosuchtv")
        self.assertEqual(code, 1)
        self.assertIn("no device called", out)


if __name__ == "__main__":
    unittest.main()
