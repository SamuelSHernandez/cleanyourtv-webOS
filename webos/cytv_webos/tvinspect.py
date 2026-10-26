"""Evidence from the TV's own web engine: a screenshot of the launcher and its state, through LG's inspector.

`ares-inspect` opens a debugging tunnel to a Developer Mode app over the same SSH session as install. Observed
with CLI 3.2.6: the tunnel listens on every network interface, not only loopback, so while it is open the app's
devtools are reachable from the local network. This module keeps it open for seconds: it reads the page id,
evaluates one fixed expression, captures one screenshot and stops the tunnel, also when anything fails.

The expression is a constant: nothing typed on the command line is ever evaluated on the TV.
"""
import base64
import json
import queue
import re
import socket
import subprocess
import threading
import time
import urllib.request

from .errors import Refused, TransportError
from .websocket import WebSocket

STATE = """JSON.stringify({ready: !!(window.CYTV && CYTV.ready), metrics: window.CYTV ? CYTV.metrics : null,
 engine: navigator.userAgent.replace(/^.*(Chrome\\/[0-9.]+).*$/, '$1'),
 source: window.CYTV && CYTV.adapter ? CYTV.adapter.inventorySource() : null,
 notice: document.getElementById('notice') && !document.getElementById('notice').hidden ? document.getElementById('notice').textContent : '',
 tiles: document.querySelectorAll('#home .tile').length,
 icons: Array.prototype.filter.call(document.querySelectorAll('#home img'), function (i) { return i.naturalWidth > 0; }).length})"""
PORT_RE = re.compile(r"localhost:(\d{2,5})|127\.0\.0\.1:(\d{2,5})|:(\d{2,5})/devtools")


def capture(device, app_id, popen=subprocess.Popen, timeout=40.0):
    """(state dict, png bytes) from the running app. The tunnel is always closed before returning."""
    proc = popen(["ares-inspect", "--device", device, "--app", app_id], stdout=subprocess.PIPE,
                 stderr=subprocess.STDOUT, text=True)
    try:
        port = _port(proc, time.monotonic() + timeout)
        page = _page(port)
        return _evaluate(port, page)
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _port(proc, deadline):
    """The tunnel's local port, from ares-inspect's output. Lines are read on a separate thread, so a CLI that
    prints nothing useful cannot hold the tunnel open past the deadline."""
    lines = queue.Queue()

    def pump():
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)
    threading.Thread(target=pump, daemon=True).start()
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TransportError("ares-inspect did not report its tunnel in time")
        try:
            line = lines.get(timeout=left)
        except queue.Empty:
            continue
        if line is None:
            raise TransportError("ares-inspect ended without opening a tunnel")
        m = PORT_RE.search(line)
        if m:
            return int(next(g for g in m.groups() if g))
        if "ERR" in line or "Error" in line:
            raise TransportError("ares-inspect failed: " + line.strip()[:200])


def _page(port):
    for _ in range(20):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as r:
                pages = json.loads(r.read(65536).decode())
            if pages and isinstance(pages[0], dict) and re.fullmatch(r"[0-9A-Fa-f-]{8,64}", str(pages[0].get("id", ""))):
                return pages[0]["id"]
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    raise TransportError("the inspector listed no page for the app")


def _evaluate(port, page):
    sock = socket.create_connection(("127.0.0.1", port), timeout=20)
    ws = WebSocket.handshake(sock, "127.0.0.1", port, "/devtools/page/" + page)
    try:
        seq = [0]

        def call(method, params):
            seq[0] += 1
            ws.send_text(json.dumps({"id": seq[0], "method": method, "params": params}))
            while True:
                m = json.loads(ws.recv_text())
                if m.get("id") == seq[0]:
                    if "error" in m:
                        raise TransportError(f"{method}: {str(m['error'])[:200]}")
                    return m["result"]
        value = call("Runtime.evaluate", {"expression": STATE, "returnByValue": True}).get("result", {}).get("value")
        state = json.loads(value) if isinstance(value, str) else {"error": "the page did not answer (scripts blocked?)"}
        png = base64.b64decode(call("Page.captureScreenshot", {"format": "png"})["data"])
        if not png.startswith(b"\x89PNG"):
            raise TransportError("the screenshot is not a PNG")
        return state, png
    finally:
        ws.close()
