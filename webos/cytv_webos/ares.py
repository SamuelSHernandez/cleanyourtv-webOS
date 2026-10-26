"""Developer Mode install transport: LG's webOS CLI (`ares-*`, npm package @webos-tools/cli).

Every call is an argument array (never a shell string), bounded by a timeout. Output formats
differ between CLI versions, so answers are parsed defensively: an answer that cannot be parsed
raises TransportError and is never read as success.

The transport is an interface; tests substitute a fake TV that implements the same methods.
"""
import re
import shutil
import subprocess

from .errors import LinkLost, Refused, TransportError, scrub
from .store import DEVICE_RE

APP_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
TOOLS = ("ares-install", "ares-launch", "ares-device")
# Answers that mean the computer never got a session with the TV, so nothing was sent.
AUTH_HINTS = ("authentication", "passphrase", "privatekey", "private key", "permission denied (publickey")
NET_HINTS = ("econnrefused", "etimedout", "ehostunreach", "enetunreach", "econnreset", "timed out",
             "no route", "socket hang up", "connection refused", "connection reset")


class PairingError(Refused):
    """The Developer Mode key or passphrase was refused (expired session, new key, wrong device)."""


def _clean(text):
    """Colour codes and the CLI's own `[Info] ...` chatter removed (observed on CLI 3.2.6: `[Info] Set target
    device : tv` is the whole answer of --listfull on a TV with no Developer Mode apps)."""
    text = re.sub(r"\x1b\[[0-9;]*m", "", text or "")
    return "\n".join(line for line in text.splitlines() if not re.match(r"\s*\[(Info|Warn|Warning)\]", line))


class AresTransport:
    def __init__(self, device, runner=subprocess.run, which=shutil.which):
        if not DEVICE_RE.fullmatch(device or ""):
            raise Refused(f"not an ares device name: {device!r}")
        self.device = device
        self._run_proc = runner
        self._which = which

    # ---- prerequisites --------------------------------------------------------------------

    def missing_tools(self):
        return [t for t in TOOLS if not self._which(t)]

    def cli_version(self):
        out = self._run(["ares-install", "--version"], 30, mutation=False)
        m = re.search(r"\d+\.\d+\.\d+", out)
        return m.group(0) if m else None

    # ---- read-only ------------------------------------------------------------------------

    def device_info(self):
        """{'modelName': ..., 'sdkVersion': ..., 'firmwareVersion': ...} as far as the TV says."""
        out = self._run(["ares-device", "--device", self.device, "--system-info"], 60, mutation=False)
        info = {}
        for line in out.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,40}", key):
                    info[key] = value.strip()[:80]
        if not info:
            raise TransportError("ares-device answered without any system information")
        return info

    def installed(self):
        """{app id: version or None} for the Developer Mode apps on the TV."""
        out = self._run(["ares-install", "--device", self.device, "--listfull"], 60, mutation=False)
        apps, current = {}, None
        for line in out.splitlines():
            m = re.match(r"\s*(id|version)\s*:\s*(\S+)\s*$", line)
            if not m:
                continue
            key, value = m.groups()
            if key == "id":
                if not APP_ID_RE.fullmatch(value):
                    raise TransportError(f"ares-install listed an id this tool cannot read: {value!r}")
                current = value
                apps[current] = None
            elif current:
                apps[current] = value
        if not apps and out.strip() and "no app" not in out.lower():
            raise TransportError("could not read the installed app list from ares-install --listfull")
        return apps

    def running(self):
        out = self._run(["ares-launch", "--device", self.device, "--running"], 60, mutation=False)
        ids = {line.strip() for line in out.splitlines() if APP_ID_RE.fullmatch(line.strip())}
        return ids

    # ---- mutations ------------------------------------------------------------------------

    def install(self, ipk_path):
        self._run(["ares-install", "--device", self.device, str(ipk_path)], 300, mutation=True)

    def remove(self, app_id):
        self._check_id(app_id)
        self._run(["ares-install", "--device", self.device, "--remove", app_id], 120, mutation=True)

    def launch(self, app_id):
        self._check_id(app_id)
        self._run(["ares-launch", "--device", self.device, app_id], 60, mutation=True)

    def close(self, app_id):
        self._check_id(app_id)
        self._run(["ares-launch", "--device", self.device, "--close", app_id], 60, mutation=True)

    # ---- plumbing -------------------------------------------------------------------------

    @staticmethod
    def _check_id(app_id):
        if not APP_ID_RE.fullmatch(app_id or ""):
            raise Refused(f"not an app id: {app_id!r}")

    def _run(self, argv, timeout, mutation):
        if not self._which(argv[0]):
            raise Refused(f"{argv[0]} is not installed. Install LG's webOS CLI: npm install -g @webos-tools/cli "
                          "(see webos/README.md for the version this was tested with)")
        try:
            proc = self._run_proc(argv, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            if mutation:
                raise LinkLost(f"{argv[0]} did not finish within {timeout}s; the outcome on the TV is unknown")
            raise TransportError(f"{argv[0]} did not finish within {timeout}s")
        except OSError as e:
            raise Refused(f"could not run {argv[0]} ({e})")
        out = _clean(proc.stdout)
        err = _clean(proc.stderr)
        if proc.returncode != 0:
            text = scrub((err or out).strip())
            low = text.lower()
            if any(h in low for h in AUTH_HINTS):
                raise PairingError("the TV refused the Developer Mode key. Check that Developer Mode is on and "
                                   "its session has not expired, then run `ares-setup-device` / "
                                   "`ares-novacom --device <name> --getkey` again.")
            if any(h in low for h in NET_HINTS):
                if mutation:
                    raise LinkLost(f"lost the TV during {argv[0]}: {text.splitlines()[-1][:200] if text else ''}")
                raise TransportError(f"cannot reach the TV: {text.splitlines()[-1][:200] if text else ''}")
            last = text.splitlines()[-1][:300] if text else f"exit status {proc.returncode}"
            raise TransportError(f"{argv[0]} failed: {last}")
        return out
