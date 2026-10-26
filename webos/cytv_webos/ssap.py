"""The TV's SSAP control channel (the protocol LG's phone apps use), from the computer.

Used read-only for the app inventory, the foreground app and system facts, and for one mutation:
`system.launcher/launch` of an app id that is in the TV's own inventory.

Trust model, stated plainly:
- The TV serves a self-signed certificate. There is no CA to check it against, so the first
  successful pairing records the certificate's SHA-256 ("trust on first use") and every later
  connection must present the same certificate. A changed certificate (a firmware update can do
  this) is refused until the owner re-pairs on purpose with `pair --repin`.
- The client key the TV issues on pairing is a credential: it is stored 0600 under the state
  directory, never printed, never written to diagnostics.
- The manifest is unsigned and asks for the smallest permission set these tools use. Which
  permission gates which URI is not documented by LG; the set below is what the reference
  projects request for the same calls. A TV may refuse an unsigned manifest; that is reported
  as a pairing refusal, never worked around.
"""
import hashlib
import json
import re
import socket
import ssl
import time

from .errors import LinkLost, Refused, TransportError, scrub
from . import store
from .websocket import WebSocket

PORT = 3001
PERMISSIONS = ["LAUNCH", "READ_INSTALLED_APPS", "READ_RUNNING_APPS", "READ_APP_STATUS",
               "READ_INPUT_DEVICE_LIST", "READ_UPDATE_INFO"]
MANIFEST = {"manifestVersion": 1, "appVersion": "1.0", "permissions": PERMISSIONS}
HOST_RE = re.compile(r"[A-Za-z0-9.-]{1,253}|\[[0-9A-Fa-f:]{2,45}\]")
APP_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
CRED_VERSION = 1


class SsapError(TransportError):
    """The TV answered with an error for one request."""


def validate_host(host):
    if not isinstance(host, str) or not HOST_RE.fullmatch(host):
        raise Refused(f"not a TV address: {host!r}")
    return host


def creds_path(device):
    return store.device_dir(device) / "ssap-credentials.json"


def load_creds(device):
    return store.load_json(creds_path(device), "SSAP credentials", CRED_VERSION)


def tls_connect(host, port=PORT, timeout=10.0):
    """A TLS socket to the TV and the SHA-256 of the certificate it presented."""
    validate_host(host)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE   # self-signed; pinned by fingerprint below instead
    try:
        raw = socket.create_connection((host.strip("[]"), port), timeout=timeout)
        sock = ctx.wrap_socket(raw, server_hostname=None)
    except (OSError, ssl.SSLError) as e:
        raise TransportError(scrub(f"cannot reach the TV's control port ({e})"))
    cert = sock.getpeercert(binary_form=True) or b""
    return sock, hashlib.sha256(cert).hexdigest()


class Session:
    """One SSAP connection. `link` is a WebSocket-like object (send_text/recv_text/close)."""

    def __init__(self, link, timeout=10.0):
        self.link = link
        self.timeout = timeout
        self._next = 0
        self._events = []   # (id, payload) for subscriptions, read while waiting for an answer

    def _id(self, prefix):
        self._next += 1
        return f"{prefix}_{self._next}"

    def _send(self, message):
        self.link.send_text(json.dumps(message))

    def _read(self):
        text = self.link.recv_text()
        try:
            message = json.loads(text)
        except ValueError:
            raise TransportError("the TV sent a message that is not JSON")
        if not isinstance(message, dict):
            raise TransportError("the TV sent a message that is not a JSON object")
        return message

    def _await(self, msg_id, accept_types, deadline):
        """Read until the answer to msg_id. Silence past the deadline is LinkLost: the request was
        sent, so whether the TV acted on it is unknown."""
        sock = getattr(self.link, "sock", None)
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise LinkLost("the TV did not answer in time")
            if sock is not None:
                sock.settimeout(left)
            try:
                message = self._read()
            except socket.timeout:
                raise LinkLost("the TV did not answer in time")
            finally:
                if sock is not None:
                    sock.settimeout(self.timeout)
            if message.get("id") != msg_id:
                self._events.append((message.get("id"), message.get("payload")))
                continue
            if message.get("type") == "error":
                raise SsapError(scrub(str(message.get("error") or "error")[:200]))
            if message.get("type") in accept_types:
                return message

    def register(self, client_key, allow_prompt, prompt_timeout=60.0):
        """Pair or re-authenticate. Returns the client key the TV confirmed."""
        msg_id = self._id("register")
        payload = {"forcePairing": False, "pairingType": "PROMPT", "manifest": MANIFEST}
        if client_key:
            payload["client-key"] = client_key
        self._send({"type": "register", "id": msg_id, "payload": payload})
        deadline = time.monotonic() + (prompt_timeout if allow_prompt else self.timeout)
        while True:
            message = self._await(msg_id, ("response", "registered"), deadline)
            if message["type"] == "registered":
                key = (message.get("payload") or {}).get("client-key")
                if not isinstance(key, str) or not key:
                    raise TransportError("the TV registered the client without a key")
                return key
            if (message.get("payload") or {}).get("pairingType") == "PROMPT" and not allow_prompt:
                raise Refused("the TV asked to show a pairing prompt; run `cytv-webos pair` first")

    def request(self, uri, payload=None):
        msg_id = self._id("req")
        self._send({"type": "request", "id": msg_id, "uri": uri, "payload": payload or {}})
        answer = self._await(msg_id, ("response",), time.monotonic() + self.timeout).get("payload") or {}
        if answer.get("returnValue") is False:
            raise SsapError(scrub(str(answer.get("errorText") or answer.get("errorCode") or "returnValue false")[:200]))
        return answer

    def subscribe(self, uri, payload=None):
        msg_id = self._id("sub")
        self._send({"type": "subscribe", "id": msg_id, "uri": uri, "payload": payload or {}})
        return msg_id

    def next_event(self, sub_id, timeout):
        """The next payload for a subscription, or None after `timeout` seconds of silence."""
        for i, (eid, payload) in enumerate(self._events):
            if eid == sub_id:
                del self._events[i]
                return payload
        sock = getattr(self.link, "sock", None)
        if sock is not None:
            sock.settimeout(timeout)
        try:
            while True:
                message = self._read()
                if message.get("id") == sub_id:
                    if message.get("type") == "error":
                        raise SsapError(scrub(str(message.get("error"))[:200]))
                    return message.get("payload") or {}
                self._events.append((message.get("id"), message.get("payload")))
        except socket.timeout:
            return None
        finally:
            if sock is not None:
                sock.settimeout(self.timeout)

    def close(self):
        self.link.close()


def connect(device, host, pair=False, repin=False, connector=None):
    """An authenticated Session. Pairing writes the credentials; otherwise they must exist.

    `connector(host)` returns (link, fingerprint); tests pass a fake one.
    """
    creds = load_creds(device)
    if not pair and not creds:
        raise Refused("this TV is not paired yet: run `cytv-webos pair` and accept the prompt on the TV")
    if connector is None:
        def connector(h):
            sock, fp = tls_connect(h)
            sock.settimeout(10.0)
            return WebSocket.handshake(sock, h.strip("[]"), PORT), fp
    link, fingerprint = connector(host)
    pinned = creds.get("cert_sha256") if creds else None
    if pinned and fingerprint != pinned and not repin:
        link.close()
        raise Refused("the TV presented a different certificate than when it was paired. That happens "
                      "after some firmware updates, and also when something else answers at that address. "
                      "If you are sure this is your TV, run `cytv-webos pair --repin`.")
    session = Session(link)
    try:
        key = session.register(creds.get("client_key") if creds else None, allow_prompt=pair)
    except BaseException:
        session.close()
        raise
    if pair or repin or not creds or creds.get("client_key") != key:
        store.write_json(creds_path(device), {"version": CRED_VERSION, "client_key": key,
                                              "cert_sha256": fingerprint,
                                              "paired": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    return session


def launch_points(session):
    """The TV's launchable apps as [{id, title, icon}] (icon: a URL the TV serves, or None)."""
    answer = session.request("ssap://com.webos.applicationManager/listLaunchPoints")
    points = answer.get("launchPoints")
    if not isinstance(points, list):
        raise TransportError("the TV's launch point list had no launchPoints")
    apps = []
    for p in points:
        if not isinstance(p, dict):
            continue
        app_id, title = p.get("id"), p.get("title")
        if not isinstance(app_id, str) or not APP_ID_RE.fullmatch(app_id):
            continue
        if not isinstance(title, str) or not title.strip():
            title = app_id
        icon = p.get("largeIcon") or p.get("icon")
        color = p.get("iconColor") or p.get("bgColor")
        apps.append({"id": app_id, "title": title.strip()[:64],
                     "icon": icon if isinstance(icon, str) else None,
                     "color": color if isinstance(color, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", color) else None,
                     "hidden": bool(p.get("hidden"))})
    return apps


def all_apps(session):
    """{app id: version or None} for every app the TV reports, system apps included."""
    answer = session.request("ssap://com.webos.applicationManager/listApps")
    apps = answer.get("apps")
    if not isinstance(apps, list):
        raise TransportError("the TV's app list had no apps")
    out = {}
    for a in apps:
        if isinstance(a, dict) and isinstance(a.get("id"), str) and APP_ID_RE.fullmatch(a["id"]):
            v = a.get("version")
            out[a["id"]] = v if isinstance(v, str) and len(v) <= 32 else None
    return out


def foreground_app(session):
    answer = session.request("ssap://com.webos.applicationManager/getForegroundAppInfo")
    app_id = answer.get("appId")
    return app_id if isinstance(app_id, str) else None


def launch(session, app_id, inventory_ids):
    """Launch an app that is in the TV's inventory. Anything else is refused before sending."""
    if not APP_ID_RE.fullmatch(app_id or "") or app_id not in inventory_ids:
        raise Refused(f"{app_id!r} is not an app this TV listed; not launching it")
    return session.request("ssap://system.launcher/launch", {"id": app_id})
