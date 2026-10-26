#!/usr/bin/env python3
"""Draw themes/aurora/wallpaper.png: teal and violet curtains of light over a navy sky, darker at the bottom.

    python3 webos/themes/aurora/make_wallpaper.py

Standard library only, and deterministic: the same script always draws the same picture, so the art is this
code (MIT) rather than a file of unknown origin. 960x540; the launcher scales it to the screen, and the picture
is soft enough that the scaling does not show.
"""
import math
from pathlib import Path
import struct
import zlib

W, H = 960, 540
OUT = Path(__file__).with_name("wallpaper.png")


def curtain(x, y, centre, width, sway, colour, strength):
    """One curtain: a vertical band whose centre sways with height, fading up and down."""
    cx = centre + sway * math.sin(y / 70.0 + centre / 90.0) + 22 * math.sin(y / 23.0)
    d = abs(x - cx) / width
    if d > 1.6:
        return (0.0, 0.0, 0.0)
    band = math.exp(-d * d * 2.2)
    rise = math.exp(-((y - 150) / 150.0) ** 2) * (0.35 + 0.65 * (1 - y / H))
    k = band * rise * strength
    return (colour[0] * k, colour[1] * k, colour[2] * k)


def pixel(x, y):
    t = y / H
    r, g, b = 7 + 6 * (1 - t), 10 + 10 * (1 - t), 20 + 26 * (1 - t)   # navy, darker toward the floor
    for c in (curtain(x, y, 300, 90, 60, (40, 220, 190), 0.55),
              curtain(x, y, 560, 120, 80, (120, 90, 230), 0.45),
              curtain(x, y, 760, 70, 50, (60, 200, 210), 0.35)):
        r, g, b = r + c[0], g + c[1], b + c[2]
    h = (x * 374761393 + y * 668265263) & 0xFFFFFFFF   # a non-linear hash: stars scatter, never line up
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    if h % 1400 == 0 and y < H * 0.6:
        glow = 50 + (h >> 20) % 70
        r, g, b = r + glow, g + glow, b + glow + 10
    return bytes((min(255, int(r)), min(255, int(g)), min(255, int(b))))


def png():
    rows = []
    for y in range(H):
        line = b"".join(pixel(x, y) for x in range(W))
        # Filter 1 (Sub): smooth gradients compress far better as differences.
        sub = bytearray(line)
        for i in range(len(line) - 1, 2, -1):
            sub[i] = (line[i] - line[i - 3]) & 0xFF
        rows.append(b"\x01" + bytes(sub))

    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!IIBBBBB", W, H, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    data = png()
    OUT.write_bytes(data)
    print(f"wrote {OUT} ({len(data) // 1024} KB)")
