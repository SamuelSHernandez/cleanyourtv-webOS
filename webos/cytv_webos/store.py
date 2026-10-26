"""Records on the computer: atomic JSON writes and per-TV locks.

Durability: a record is written to a fresh temporary file in the same directory, flushed, fsync'd,
renamed over the old one, and then the directory is fsync'd where the OS allows it (POSIX). That
protects against a crash leaving a half-written record. It does not prove the record survives a power
cut on every filesystem: some filesystems and disks acknowledge fsync before the data is stable. A
record that fails to parse is never repaired or replaced automatically (see `load_json`).

Locks are advisory `flock` locks on POSIX: the kernel releases them when the holder exits or crashes,
so a crash never leaves a stale lock behind. Where `fcntl` is missing (Windows) an exclusive-create
lock file is used instead, and a lock left by a crash must be deleted by hand.
"""
import errno
import json
import os
from pathlib import Path
import re
import tempfile
import time

from .errors import Refused

try:
    import fcntl
except ImportError:   # Windows
    fcntl = None

DEVICE_RE = re.compile(r"[A-Za-z0-9_-]{1,32}")


def state_root():
    """Where records live: $CYTV_WEBOS_HOME, else ~/.cleanyourtv-webos."""
    base = os.environ.get("CYTV_WEBOS_HOME")
    return Path(base) if base else Path.home() / ".cleanyourtv-webos"


def device_dir(device):
    """The folder for one TV. The name is checked here, so no record can land outside the state root."""
    if not isinstance(device, str) or not DEVICE_RE.fullmatch(device):
        raise Refused(f"device names are 1-32 letters, digits, _ or -; got {device!r}")
    return state_root() / device


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _fsync_dir(path.parent)


def _fsync_dir(directory):
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass  # Not supported on every OS (Windows); the rename itself has already happened.
    finally:
        os.close(fd)


def load_json(path, kind, version):
    """Read a record. Missing: None. Corrupt or another version: Refused, and the file is left as is."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as e:
        raise Refused(f"{path}: cannot read the {kind} ({e.strerror or e}).")
    try:
        data = json.loads(text)
    except ValueError as e:
        raise Refused(f"{path}: not a usable {kind} ({e}). It was left where it is: it may hold the only "
                      "copy of the state before installation. Move it aside deliberately to continue.")
    if not isinstance(data, dict) or data.get("version") != version:
        found = data.get("version") if isinstance(data, dict) else type(data).__name__
        raise Refused(f"{path}: {kind} format {found!r} is not the supported version {version}. It was "
                      "left where it is; use the tool version that wrote it, or move it aside deliberately.")
    return data


class ProcessLock:
    """An exclusive lock on `path` for this process. `wait` seconds to get it, then Refused(busy)."""

    def __init__(self, path, busy, wait=0.0):
        self.path = Path(path)
        self.busy = busy
        self.wait = wait
        self.fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        deadline = time.monotonic() + self.wait
        while True:
            if self._try():
                return self
            if time.monotonic() >= deadline:
                raise Refused(self.busy)
            time.sleep(0.05)

    def _try(self):
        if fcntl is not None:
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                os.close(fd)
                return False
            os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode())
            self.fd = fd
            return True
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
            return False
        os.write(fd, str(os.getpid()).encode())
        self.fd = fd
        return True

    def __exit__(self, *exc):
        if self.fd is None:
            return False
        if fcntl is not None:
            fcntl.flock(self.fd, fcntl.LOCK_UN)   # the file stays; only the lock matters
            os.close(self.fd)
        else:
            os.close(self.fd)
            try:
                os.unlink(self.path)
            except OSError:
                pass
        self.fd = None
        return False


def DeviceLock(device):
    """One install/restore/status run per TV at a time, across processes."""
    hint = "" if fcntl else (" If no run is active, a crash left the lock behind: delete "
                             f"{device_dir(device) / 'lock'} deliberately.")
    return ProcessLock(device_dir(device) / "lock",
                       "another cytv-webos run is working on this TV. Wait for it to finish; nothing was "
                       "changed by this run." + hint)
