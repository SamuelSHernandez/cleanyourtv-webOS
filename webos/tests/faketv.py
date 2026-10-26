"""A simulated TV behind the transport interface, with fault injection.

It keeps state the way a TV would (installed apps and versions, running apps) and records every
call, so tests can assert both the outcome and what was, or was not, sent.
"""
from pathlib import Path
import os
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cytv_webos import build  # noqa: E402
from cytv_webos.ares import PairingError  # noqa: E402
from cytv_webos.errors import LinkLost, TransportError  # noqa: E402

FACTS = {"modelName": "OLED55C3", "sdkVersion": "8.2.0", "firmwareVersion": "33.21.71",
         # Private values a real TV answers with; the report must never carry them.
         "serialNumber": "SERIAL-SHOULD-NOT-LEAK", "macAddress": "aa:bb:cc:dd:ee:ff"}


class FakeTV:
    def __init__(self, **faults):
        self.installed_apps = {}
        self.running_apps = set()
        self.facts = dict(FACTS)
        self.missing = []
        self.calls = []
        self.faults = dict(faults)
        self.on_call = None   # hook(name) to change state between calls (concurrent changes)

    def _call(self, name):
        self.calls.append(name)
        if self.on_call:
            self.on_call(name)
        if self.faults.get("pairing_refused"):
            raise PairingError("the TV refused the Developer Mode key")

    def mutations(self):
        return [c for c in self.calls if c.split(":")[0] in ("install", "remove", "launch", "close")]

    # read-only
    def missing_tools(self):
        return list(self.missing)

    def cli_version(self):
        self._call("cli_version")
        return "3.2.1"

    def device_info(self):
        self._call("device_info")
        if self.faults.get("unreachable"):
            raise TransportError("cannot reach the TV: ECONNREFUSED")
        return dict(self.facts)

    def installed(self):
        self._call("installed")
        if self.faults.get("readback_fails") and any(c.startswith(("install:", "remove:")) for c in self.calls):
            raise TransportError("cannot reach the TV: ETIMEDOUT")
        return dict(self.installed_apps)

    def running(self):
        self._call("running")
        return set(self.running_apps)

    # mutations
    def install(self, ipk_path):
        self._call(f"install:{Path(ipk_path).name}")
        info = build.verify(ipk_path)
        if self.faults.get("install_rejected"):
            raise TransportError("ares-install failed: FAILED_IPKG_INSTALL: package verification failed")
        if self.faults.get("storage_full"):
            raise TransportError("ares-install failed: Installation failure: not enough space")
        if self.faults.get("link_lost_before_install"):
            raise LinkLost("lost the TV during ares-install: ECONNRESET")
        self.installed_apps[info["id"]] = info["version"]
        if self.faults.get("link_lost_after_install"):
            raise LinkLost("lost the TV during ares-install: ECONNRESET")
        if self.faults.get("install_reports_error_but_installed"):
            raise TransportError("ares-install failed: unexpected end of output")

    def remove(self, app_id):
        self._call(f"remove:{app_id}")
        if self.faults.get("remove_fails"):
            raise TransportError("ares-install failed: FAILED_REMOVE")
        self.installed_apps.pop(app_id, None)
        self.running_apps.discard(app_id)
        if self.faults.get("link_lost_after_remove"):
            raise LinkLost("lost the TV during ares-install: ECONNRESET")

    def launch(self, app_id):
        self._call(f"launch:{app_id}")
        if self.faults.get("launch_fails") or app_id not in self.installed_apps:
            raise TransportError("ares-launch failed: app not found")
        if not self.faults.get("launch_ack_without_run"):
            self.running_apps.add(app_id)

    def close(self, app_id):
        self._call(f"close:{app_id}")
        self.running_apps.discard(app_id)


class StateDir:
    """Points CYTV_WEBOS_HOME at a fresh temporary folder for one test."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("CYTV_WEBOS_HOME")
        os.environ["CYTV_WEBOS_HOME"] = self.tmp.name
        return Path(self.tmp.name)

    def __exit__(self, *exc):
        if self.old is None:
            os.environ.pop("CYTV_WEBOS_HOME", None)
        else:
            os.environ["CYTV_WEBOS_HOME"] = self.old
        self.tmp.cleanup()
        return False


_IPK = None


def launcher_ipk():
    """The real launcher package, built once per test run into a temporary folder."""
    global _IPK
    if _IPK is None:
        out = Path(tempfile.mkdtemp(prefix="cytv-ipk-"))
        path, _, info = build.build(None, out)
        _IPK = (path, info)
    return _IPK


def variant_ipk(app_id=None, version=None):
    """The launcher package with another id or version, as a different or newer build would be."""
    import json
    import shutil
    from cytv_webos import ipk
    src = Path(tempfile.mkdtemp(prefix="cytv-variant-")) / "app"
    stage, _ = build.stage(None, src.parent)
    shutil.copytree(stage, src)
    info = json.loads((src / "appinfo.json").read_text())
    info["id"] = app_id or info["id"]
    info["version"] = version or info["version"]
    (src / "appinfo.json").write_text(json.dumps(info))
    path, _, info = ipk.build(src, src.parent / "out")
    return path, info
