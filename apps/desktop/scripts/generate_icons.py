"""Generate MVR2T's app icon (black rounded square, white rabbit-head silhouette, bold M inside).

Outputs (committed to the repo; re-run after changing this script):
    apps/desktop/build/icon.ico     16, 32, 48, 256 px — Windows window/taskbar icon and installer (Phase 11)
    apps/desktop/build/icon.png     512 px — window icon on macOS / Linux
    apps/desktop/public/favicon.ico 16, 32, 48 px — page icon

Large sizes are drawn from vector shapes with 4x4 supersampling. 16 and 32 px are hand-made pixel art
(simplified ears, M strokes 2-3 px wide) so they stay crisp in the taskbar.

Standard library only (no Pillow needed):
    python apps/desktop/scripts/generate_icons.py
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLACK = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)
CLEAR = (0, 0, 0, 0)

# --- vector design, in a 256 x 256 box ------------------------------------------------------------


def _rotate(px: float, py: float, cx: float, cy: float, deg: float) -> tuple[float, float]:
    a = math.radians(deg)
    dx, dy = px - cx, py - cy
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)


def _seg_dist(px: float, py: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    ax, ay = a
    bx, by = b
    vx, vy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy)))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


# Ears: capsules (radius 20) leaning outwards by 8 degrees around their base
EARS = [
    (_rotate(98, 40, 98, 120, -8), (98, 120)),
    (_rotate(158, 40, 158, 120, 8), (158, 120)),
]
M_PATH = [(90, 196), (90, 128), (128, 170), (166, 128), (166, 196)]


def vector_color(x: float, y: float) -> tuple[int, int, int, int]:
    # rounded-square background (radius 56)
    r = 56
    cx = min(max(x, r), 256 - r)
    cy = min(max(y, r), 256 - r)
    if math.hypot(x - cx, y - cy) > r:
        return CLEAR
    in_m = y <= 196 and any(_seg_dist(x, y, M_PATH[i], M_PATH[i + 1]) <= 12 for i in range(len(M_PATH) - 1))
    in_head = ((x - 128) / 84) ** 2 + ((y - 158) / 72) ** 2 <= 1
    if in_head and in_m:
        return BLACK
    if in_head or any(_seg_dist(x, y, a, b) <= 20 for a, b in EARS):
        return WHITE
    return BLACK


def render_vector(size: int, ss: int = 4) -> list[list[tuple[int, int, int, int]]]:
    scale = 256 / size
    out = []
    for py in range(size):
        row = []
        for px in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(ss):
                for sx in range(ss):
                    c = vector_color((px + (sx + 0.5) / ss) * scale, (py + (sy + 0.5) / ss) * scale)
                    a = c[3]
                    acc[0] += c[0] * a
                    acc[1] += c[1] * a
                    acc[2] += c[2] * a
                    acc[3] += a
            n = ss * ss
            alpha = acc[3] / n
            if alpha == 0:
                row.append(CLEAR)
            else:
                row.append((round(acc[0] / acc[3]), round(acc[1] / acc[3]), round(acc[2] / acc[3]), round(alpha)))
        out.append(row)
    return out


# --- hand-made pixel art for small sizes ----------------------------------------------------------


def pixel16() -> list[list[tuple[int, int, int, int]]]:
    g = [["K"] * 16 for _ in range(16)]
    for x, y in [(0, 0), (1, 0), (0, 1), (15, 0), (14, 0), (15, 1), (0, 15), (1, 15), (0, 14), (15, 15), (14, 15), (15, 14)]:
        g[y][x] = "."
    for y in range(1, 6):  # ears: 2 px wide
        for x in (4, 5, 10, 11):
            g[y][x] = "W"
    head = {5: (4, 11), 6: (2, 13), 7: (1, 14), 8: (1, 14), 9: (1, 14), 10: (1, 14), 11: (1, 14), 12: (2, 13), 13: (3, 12)}
    for y, (a, b) in head.items():
        for x in range(a, b + 1):
            g[y][x] = "W"
    m = ["KK....KK", "KKK..KKK", "KK.KK.KK", "KK....KK", "KK....KK"]
    for dy, r in enumerate(m):
        for dx, c in enumerate(r):
            if c == "K":
                g[7 + dy][4 + dx] = "K"
    return _to_rgba(g)


def pixel32() -> list[list[tuple[int, int, int, int]]]:
    g = [["K"] * 32 for _ in range(32)]
    for y in range(32):
        for x in range(32):
            cx, cy = min(x, 31 - x), min(y, 31 - y)
            if cx < 5 and cy < 5 and (5 - cx) ** 2 + (5 - cy) ** 2 > 26:
                g[y][x] = "."
    for y in range(3, 13):  # ears: 4 px wide, top tilted outwards
        off = 1 if y < 6 else 0
        for x in range(9 - off, 13 - off):
            g[y][x] = "W"
        for x in range(19 + off, 23 + off):
            g[y][x] = "W"
    for y in range(9, 29):
        for x in range(32):
            if ((x + 0.5 - 16) / 12.6) ** 2 + ((y + 0.5 - 19.5) / 9.6) ** 2 <= 1:
                g[y][x] = "W"
    m = ["KKK......KKK", "KKKK....KKKK", "KKKKK..KKKKK", "KKK.KKKK.KKK", "KKK..KK..KKK", "KKK......KKK", "KKK......KKK"]
    for dy, r in enumerate(m):
        for dx, c in enumerate(r):
            if c == "K":
                g[14 + dy][10 + dx] = "K"
    return _to_rgba(g)


def _to_rgba(g: list[list[str]]) -> list[list[tuple[int, int, int, int]]]:
    return [[BLACK if c == "K" else WHITE if c == "W" else CLEAR for c in row] for row in g]


# --- encoders --------------------------------------------------------------------------------------


def png_bytes(pixels: list[list[tuple[int, int, int, int]]]) -> bytes:
    h, w = len(pixels), len(pixels[0])
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px) for row in pixels)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def ico_bytes(images: dict[int, bytes]) -> bytes:
    """ICO with PNG-encoded entries (supported since Windows Vista)."""
    sizes = sorted(images)
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, data = b"", b""
    for s in sizes:
        png = images[s]
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    return header + entries + data


def main() -> None:
    frames = {16: png_bytes(pixel16()), 32: png_bytes(pixel32()), 48: png_bytes(render_vector(48)), 256: png_bytes(render_vector(256))}
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "public").mkdir(exist_ok=True)
    (ROOT / "build" / "icon.ico").write_bytes(ico_bytes(frames))
    (ROOT / "build" / "icon.png").write_bytes(png_bytes(render_vector(512, ss=3)))
    (ROOT / "public" / "favicon.ico").write_bytes(ico_bytes({s: frames[s] for s in (16, 32, 48)}))
    print("wrote build/icon.ico, build/icon.png, public/favicon.ico")


if __name__ == "__main__":
    main()
