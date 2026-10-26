"""Which TV a name refers to: the ares device name and the TV's address for SSAP."""
from .errors import Refused
from . import ares, ssap, store

VERSION = 1


def path_for(name):
    return store.device_dir(name) / "device.json"


def save(name, host):
    if not ares.DEVICE_RE.fullmatch(name or ""):
        raise Refused(f"device names are 1-32 letters, digits, _ or -; got {name!r}")
    ssap.validate_host(host)
    store.write_json(path_for(name), {"version": VERSION, "name": name, "host": host})


def load(name):
    if not ares.DEVICE_RE.fullmatch(name or ""):
        raise Refused(f"not a device name: {name!r}")
    data = store.load_json(path_for(name), "device record", VERSION)
    if data is None:
        raise Refused(f"no device called {name!r}: run `cytv-webos setup --device {name} --host <tv ip>` first "
                      "(the same name you gave ares-setup-device)")
    ssap.validate_host(data.get("host"))
    return data


def remember_theme(name, theme):
    """The theme folder the launcher was last installed with (or None), so later rebuilds keep it."""
    data = load(name)
    data["theme"] = str(theme) if theme else None
    store.write_json(path_for(name), data)


def last_theme(name):
    t = load(name).get("theme")
    return t if isinstance(t, str) and t else None
