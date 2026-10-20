
"""
Generate ShopLedger PWA icons (icon-192.png, icon-512.png) into static/.
Pure standard library - no Pillow needed. Run once:  python make_icons.py
Draws a ledger book (violet-pink gradient cover, white pages) on dark navy.
"""

import os
import struct
import zlib


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rounded_rect(x, y, x0, y0, x1, y1, r):
    """True if point (x, y) is inside the rounded rectangle."""
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r or (
        x0 + r <= x <= x1 - r or y0 + r <= y <= y1 - r
    )


def pixel(x, y, s):
    """Color of one pixel of an s x s icon."""
    u, v = x / s, y / s
    # background: dark navy diagonal gradient
    col = lerp((10, 14, 26), (26, 20, 48), (u + v) / 2)

    # book cover: violet -> pink, rounded
    if rounded_rect(u, v, 0.20, 0.25, 0.80, 0.75, 0.05):
        col = lerp((139, 92, 246), (236, 72, 153), u)
    # pages: off-white, inset
    if rounded_rect(u, v, 0.26, 0.30, 0.74, 0.70, 0.03):
        col = (241, 245, 249)
    # center spine
    if 0.494 <= u <= 0.506 and 0.30 <= v <= 0.70:
        col = (15, 23, 42)
    # text lines on both pages
    for ly in (0.40, 0.47, 0.54, 0.61):
        if ly <= v <= ly + 0.018:
            if 0.31 <= u <= 0.46 or 0.54 <= u <= 0.69:
                col = (100, 116, 139)
    return col + (255,)


def write_png(path, size):
    raw = b""
    for y in range(size):
        raw += b"\x00" + b"".join(
            struct.pack("BBBB", *pixel(x, y, size)) for x in range(size)
        )

    def chunk(typ, data):
        out = struct.pack(">I", len(data)) + typ + data
        out += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        return out

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    with open(path, "wb") as f:
        f.write(png)
    print("wrote", path)


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    static = os.path.join(here, "static")
    os.makedirs(static, exist_ok=True)
    write_png(os.path.join(static, "icon-192.png"), 192)
    write_png(os.path.join(static, "icon-512.png"), 512)