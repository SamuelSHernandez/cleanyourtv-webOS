"""A minimal RFC 6455 WebSocket client (text frames only), standard library only.

Enough for the TV's SSAP endpoint: client-masked text frames, ping/pong, close, and a bound on
message size. No extensions, no compression, no proxies.
"""
import base64
import hashlib
import os
import socket
import struct

from .errors import LinkLost, TransportError

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_MESSAGE = 4 * 1024 * 1024   # an app list with many launch points stays far below this


class WebSocket:
    def __init__(self, sock):
        self.sock = sock
        self._buf = b""
        self._partial = b""   # fragments of a message whose last frame has not arrived yet

    @classmethod
    def handshake(cls, sock, host, port, path="/"):
        key = base64.b64encode(os.urandom(16)).decode()
        request = (f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                   f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        sock.sendall(request.encode())
        ws = cls(sock)
        head = ws._read_until(b"\r\n\r\n", 16384)
        lines = head.decode("latin-1").split("\r\n")
        if not lines or " 101 " not in lines[0] + " ":
            raise TransportError(f"the TV refused the WebSocket upgrade: {lines[0] if lines else 'no answer'}")
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        expected = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        if headers.get("sec-websocket-accept") != expected:
            raise TransportError("the WebSocket handshake answer did not match the request")
        return ws

    def _recv(self, n):
        try:
            data = self.sock.recv(n)
        except socket.timeout:
            raise
        except OSError as e:
            raise LinkLost(f"connection lost ({e})")
        if not data:
            raise LinkLost("the TV closed the connection")
        return data

    def _read_until(self, marker, limit):
        while marker not in self._buf:
            if len(self._buf) > limit:
                raise TransportError("answer too large")
            self._buf += self._recv(4096)
        head, _, self._buf = self._buf.partition(marker)
        return head

    def send_text(self, text):
        self._send(0x1, text.encode("utf-8"))

    def _send(self, opcode, payload):
        header = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack("!H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", n)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        try:
            self.sock.sendall(header + mask + masked)
        except OSError as e:
            raise LinkLost(f"connection lost while sending ({e})")

    def _frame(self):
        """Take one complete frame off the buffer, or return None and consume nothing.

        Nothing is removed until the whole frame has arrived, so a socket timeout in the middle of a
        frame (the watcher reads with a one-second timeout) leaves the stream intact for the next read.
        """
        buf = self._buf
        if len(buf) < 2:
            return None
        b1, b2 = buf[0], buf[1]
        n, pos = b2 & 0x7F, 2
        if n == 126:
            if len(buf) < 4:
                return None
            n, pos = struct.unpack("!H", buf[2:4])[0], 4
        elif n == 127:
            if len(buf) < 10:
                return None
            n, pos = struct.unpack("!Q", buf[2:10])[0], 10
        if n > MAX_MESSAGE or len(self._partial) + n > MAX_MESSAGE:
            raise TransportError("message from the TV exceeds the size limit")
        mask = None
        if b2 & 0x80:
            if len(buf) < pos + 4:
                return None
            mask, pos = buf[pos:pos + 4], pos + 4
        if len(buf) < pos + n:
            return None
        payload, self._buf = buf[pos:pos + n], buf[pos + n:]
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return b1 & 0x80, b1 & 0x0F, payload

    def recv_text(self):
        """The next text message. Answers pings; raises LinkLost on close. A socket timeout can
        interrupt it at any point without losing data: the next call resumes where this one stopped."""
        while True:
            frame = self._frame()
            if frame is None:
                self._buf += self._recv(65536)
                continue
            fin, opcode, payload = frame
            if opcode == 0x8:
                raise LinkLost("the TV closed the connection")
            if opcode == 0x9:
                self._send(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode not in (0x1, 0x0):
                raise TransportError(f"unexpected WebSocket opcode {opcode}")
            self._partial += payload
            if not fin:
                continue
            message, self._partial = self._partial, b""
            try:
                return message.decode("utf-8")
            except UnicodeDecodeError:
                raise TransportError("the TV sent a message that is not UTF-8")

    def close(self):
        try:
            self._send(0x8, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
