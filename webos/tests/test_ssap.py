"""The WebSocket client against a local server, and the SSAP session and pairing logic."""
import base64
import hashlib
import json
import os
import socket
import struct
import threading
import time
import unittest

from faketv import StateDir

from cytv_webos import ssap, websocket
from cytv_webos.errors import LinkLost, Refused, TransportError


def server_frame(text, opcode=0x1, fin=True):
    data = text.encode() if isinstance(text, str) else text
    head = bytes([(0x80 if fin else 0) | opcode])
    if len(data) < 126:
        head += bytes([len(data)])
    elif len(data) < 65536:
        head += bytes([126]) + struct.pack("!H", len(data))
    else:
        head += bytes([127]) + struct.pack("!Q", len(data))
    return head + data


def read_client_frame(conn):
    b1, b2 = conn.recv(2)
    n = b2 & 0x7F
    if n == 126:
        n = struct.unpack("!H", conn.recv(2))[0]
    mask = conn.recv(4)
    data = b""
    while len(data) < n:
        data += conn.recv(n - len(data))
    return b1 & 0x0F, bytes(b ^ mask[i % 4] for i, b in enumerate(data))


class LocalServer:
    """A plain-TCP WebSocket server that runs one scripted conversation."""

    def __init__(self, script):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.script = script
        self.received = []
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        conn, _ = self.sock.accept()
        req = b""
        while b"\r\n\r\n" not in req:
            req += conn.recv(1024)
        key = [l.split(":", 1)[1].strip() for l in req.decode().split("\r\n") if l.lower().startswith("sec-websocket-key")][0]
        accept = base64.b64encode(hashlib.sha1((key + websocket.GUID).encode()).digest()).decode()
        conn.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
        for step in self.script:
            if step == "recv":
                self.received.append(read_client_frame(conn))
            elif isinstance(step, float):
                time.sleep(step)
            else:
                conn.sendall(step)
        conn.close()
        self.sock.close()


def client(server):
    s = socket.create_connection(("127.0.0.1", server.port), timeout=5)
    return websocket.WebSocket.handshake(s, "127.0.0.1", server.port)


class WebSocketTest(unittest.TestCase):
    def client(self, srv):
        ws = client(srv)
        self.addCleanup(ws.close)
        self.addCleanup(srv.thread.join, 5)
        return ws

    def test_text_round_trip_with_ping_and_fragments(self):
        srv = LocalServer(["recv", server_frame(b"ping!", opcode=0x9),
                           server_frame("hel", fin=False), server_frame("lo", opcode=0x0), "recv"])
        ws = self.client(srv)
        ws.send_text("x" * 300)
        self.assertEqual(ws.recv_text(), "hello")
        srv.thread.join(5)
        self.assertEqual(srv.received[0], (0x1, b"x" * 300))
        self.assertEqual(srv.received[1], (0xA, b"ping!"), "a ping is answered with its payload")

    def test_a_timeout_in_the_middle_of_a_frame_loses_nothing(self):
        frame = server_frame('{"type":"response","id":"x"}')
        srv = LocalServer([frame[:5], 0.5, frame[5:], 0.3])
        ws = self.client(srv)
        ws.sock.settimeout(0.1)
        with self.assertRaises(socket.timeout):
            ws.recv_text()
        ws.sock.settimeout(5)
        self.assertEqual(ws.recv_text(), '{"type":"response","id":"x"}')

    def test_close_frame_is_link_lost(self):
        srv = LocalServer([server_frame(b"", opcode=0x8)])
        ws = self.client(srv)
        with self.assertRaises(LinkLost):
            ws.recv_text()

    def test_oversized_message_is_refused(self):
        srv = LocalServer([bytes([0x81, 127]) + struct.pack("!Q", websocket.MAX_MESSAGE + 1)])
        ws = self.client(srv)
        with self.assertRaises(TransportError):
            ws.recv_text()

    def test_wrong_accept_header_is_refused(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]

        def bad():
            c, _ = sock.accept()
            c.recv(1024)
            c.sendall(b"HTTP/1.1 101 OK\r\nSec-WebSocket-Accept: nope\r\n\r\n")
            c.close()
            sock.close()
        threading.Thread(target=bad, daemon=True).start()
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.addCleanup(s.close)
        with self.assertRaises(TransportError):
            websocket.WebSocket.handshake(s, "127.0.0.1", port)


class FakeLink:
    def __init__(self, answers):
        self.answers = list(answers)
        self.sent = []
        self.closed = False

    def send_text(self, text):
        msg = json.loads(text)
        self.sent.append(msg)
        for a in self.answers.pop(0) if self.answers else []:
            a = dict(a)
            a.setdefault("id", msg["id"])
            self.pending.append(json.dumps(a))

    pending = None

    def recv_text(self):
        if not self.pending:
            raise LinkLost("closed")
        return self.pending.pop(0)

    def close(self):
        self.closed = True


def link(*answers):
    l = FakeLink(answers)
    l.pending = []
    return l


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.s = StateDir()
        self.root = self.s.__enter__()

    def tearDown(self):
        self.s.__exit__(None, None, None)

    def test_pairing_asks_minimal_permissions_and_stores_key_privately(self):
        l = link([{"type": "response", "payload": {"pairingType": "PROMPT"}},
                  {"type": "registered", "payload": {"client-key": "SECRET-KEY"}}])
        session = ssap.connect("tv", "192.168.1.50", pair=True, connector=lambda h: (l, "ab" * 32))
        perms = l.sent[0]["payload"]["manifest"]["permissions"]
        self.assertNotIn("CONTROL_POWER", perms)
        self.assertNotIn("CONTROL_MOUSE_AND_KEYBOARD", perms)
        self.assertNotIn("signatures", l.sent[0]["payload"]["manifest"])
        creds = ssap.load_creds("tv")
        self.assertEqual(creds["client_key"], "SECRET-KEY")
        self.assertEqual(os.stat(ssap.creds_path("tv")).st_mode & 0o777, 0o600)
        session.close()

    def test_unpaired_tv_is_refused_without_a_prompt(self):
        with self.assertRaises(Refused):
            ssap.connect("tv", "192.168.1.50", connector=lambda h: (link(), "ab" * 32))

    def test_prompt_without_pairing_is_refused(self):
        self._paired()
        l = link([{"type": "response", "payload": {"pairingType": "PROMPT"}}])
        with self.assertRaises(Refused):
            ssap.connect("tv", "192.168.1.50", connector=lambda h: (l, "ab" * 32))
        self.assertTrue(l.closed)

    def test_changed_certificate_is_refused_unless_repinned(self):
        self._paired()
        with self.assertRaises(Refused) as ctx:
            ssap.connect("tv", "192.168.1.50", connector=lambda h: (link(), "cd" * 32))
        self.assertIn("different certificate", str(ctx.exception))
        l = link([{"type": "registered", "payload": {"client-key": "K2"}}])
        ssap.connect("tv", "192.168.1.50", repin=True, connector=lambda h: (l, "cd" * 32))
        self.assertEqual(ssap.load_creds("tv")["cert_sha256"], "cd" * 32)

    def test_revoked_key_is_an_error_not_success(self):
        self._paired()
        l = link([{"type": "error", "error": "401 insufficient permissions"}])
        with self.assertRaises(TransportError):
            ssap.connect("tv", "192.168.1.50", connector=lambda h: (l, "ab" * 32))

    def test_launch_only_of_listed_apps(self):
        session = ssap.Session(link())
        for bad in ("com.evil", "-rf", "x;y", ""):
            with self.assertRaises(Refused):
                ssap.launch(session, bad, {"netflix"})

    def test_returnvalue_false_is_an_error(self):
        session = ssap.Session(link([{"type": "response", "payload": {"returnValue": False, "errorText": "no"}}]))
        with self.assertRaises(ssap.SsapError):
            session.request("ssap://system.launcher/launch", {"id": "netflix"})

    def test_subscription_events_arriving_during_a_request_are_kept(self):
        l = link()
        session = ssap.Session(l)
        sub = session.subscribe("ssap://com.webos.applicationManager/getForegroundAppInfo")
        l.pending = [json.dumps({"type": "response", "id": sub, "payload": {"appId": "netflix"}}),
                     json.dumps({"type": "response", "id": "req_2", "payload": {"returnValue": True, "apps": []}})]
        self.assertEqual(ssap.all_apps(session), {})
        self.assertEqual(session.next_event(sub, 0.1), {"appId": "netflix"})

    def test_launch_points_drop_malformed_entries(self):
        session = ssap.Session(link([{"type": "response", "payload": {"returnValue": True, "launchPoints": [
            {"id": "netflix", "title": "Netflix", "icon": "http://x/i.png"},
            {"id": "bad id; rm", "title": "x"}, "junk", {"id": "youtube.leanback.v4"}]}}]))
        apps = ssap.launch_points(session)
        self.assertEqual([a["id"] for a in apps], ["netflix", "youtube.leanback.v4"])
        self.assertEqual(apps[1]["title"], "youtube.leanback.v4")

    def test_silence_after_a_request_is_link_lost_not_a_raw_timeout(self):
        class SilentSock:
            def settimeout(self, t):
                pass

        class SilentLink:
            sock = SilentSock()

            def send_text(self, text):
                pass

            def recv_text(self):
                raise socket.timeout()

            def close(self):
                pass
        session = ssap.Session(SilentLink(), timeout=0.05)
        with self.assertRaises(LinkLost):
            session.request("ssap://system.launcher/launch", {"id": "netflix"})
        with self.assertRaises(LinkLost):
            session.register("K", allow_prompt=True, prompt_timeout=0.05)

    def test_host_validation(self):
        for bad in ("192.168.1.50; rm", "", "a b", "http://x"):
            with self.assertRaises(Refused):
                ssap.validate_host(bad)

    def _paired(self):
        l = link([{"type": "registered", "payload": {"client-key": "K"}}])
        ssap.connect("tv", "192.168.1.50", pair=True, connector=lambda h: (l, "ab" * 32))


if __name__ == "__main__":
    unittest.main()
