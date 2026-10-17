#!/usr/bin/env python3
"""Generuje ikony PWA. Czysty Python, bez PIL i bez Node.

    python3 tools/make_icons.py

Rysuje tortownik (forma do tortu) na gradiencie w kolorze akcentu aplikacji.
Krawedzie wygladzane 3x nadprobkowaniem - bez tego ikona ma zabkowane brzegi.
"""
import math
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
OUT = os.path.join(ROOT, "docs", "icons")

SS = 3                                   # nadprobkowanie na os
TOP = (0x00, 0x9E, 0xE0)                 # gradient od
BOTTOM = (0x00, 0x6B, 0xA3)              # gradient do
INK = (255, 255, 255)


# ───────────────────── zapis PNG ─────────────────────

def write_png(path, width, height, rows):
    """rows: lista bytearray dlugosci width*4 (RGBA)."""
    raw = bytearray()
    for row in rows:
        raw.append(0)                    # filtr: None
        raw += row

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


# ───────────────────── geometria ─────────────────────

def rrect(x, y, x0, y0, x1, y1, r):
    """Czy punkt lezy w prostokacie o zaokraglonych narozach."""
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r or (x0 + r <= x <= x1 - r) or (y0 + r <= y <= y1 - r)


def glyph(x, y):
    """Tortownik w ukladzie 0..1. Zwraca True dla punktow nalezacych do znaku."""
    # Podstawa (blat stolu)
    if rrect(x, y, 0.16, 0.805, 0.84, 0.845, 0.020):
        return True

    # Korpus formy: lekko zwezajacy sie ku dolowi
    if 0.555 <= y <= 0.800:
        t = (y - 0.555) / 0.245
        half = 0.300 - 0.022 * t
        if abs(x - 0.5) <= half:
            return True

    # Falbana polewy na gorze korpusu: 6 polkoli
    scallops = 6
    span = 0.600
    r = span / (2 * scallops)
    for i in range(scallops):
        cx = 0.5 - span / 2 + r + 2 * r * i
        if (x - cx) ** 2 + (y - 0.555) ** 2 <= r * r and y <= 0.555:
            return True

    # Swieczka
    if rrect(x, y, 0.484, 0.350, 0.516, 0.505, 0.014):
        return True

    # Plomien: okragla podstawa + zwezajacy sie czubek, zeby czytal sie
    # jako ogien, a nie jako kropka nad swieczka.
    R, BASE, APEX = 0.039, 0.352, 0.252
    cy = BASE - R
    fx = x - 0.5
    if y >= cy:                                     # dolna polowa: kolo
        if fx * fx + (y - cy) ** 2 <= R * R:
            return True
    elif y >= APEX:                                 # gorna: zwezenie do czubka
        half = R * ((y - APEX) / (cy - APEX)) ** 0.62
        if abs(fx) <= half:
            return True
    return False


def render(size, inset=0.0, rounded=False):
    """inset: margines dla ikony maskowalnej (bezpieczna strefa)."""
    n = size * SS
    rows = []
    scale = 1.0 - 2 * inset
    radius = 0.2237 * n                             # proporcja naroza iOS

    for py in range(size):
        row = bytearray()
        for px in range(size):
            r_acc = g_acc = b_acc = a_acc = 0
            for sy in range(SS):
                for sx in range(SS):
                    fx = (px * SS + sx + 0.5) / n
                    fy = (py * SS + sy + 0.5) / n

                    if rounded:
                        qx, qy = fx * n, fy * n
                        cx = min(max(qx, radius), n - radius)
                        cy = min(max(qy, radius), n - radius)
                        if (qx - cx) ** 2 + (qy - cy) ** 2 > radius * radius:
                            continue                # poza zaokraglonym kwadratem

                    # tlo: gradient pionowy z lekkim przesunieciem w poziomie
                    t = min(1.0, max(0.0, fy * 0.82 + fx * 0.18))
                    bg = tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))

                    gx = (fx - 0.5) / scale + 0.5
                    gy = (fy - 0.5) / scale + 0.5
                    col = INK if (0 <= gx <= 1 and 0 <= gy <= 1 and glyph(gx, gy)) else bg

                    r_acc += col[0]; g_acc += col[1]; b_acc += col[2]; a_acc += 255

            total = SS * SS
            if a_acc == 0:
                row += bytes((0, 0, 0, 0))
            else:
                cov = a_acc / 255
                row += bytes((round(r_acc / cov), round(g_acc / cov),
                              round(b_acc / cov), round(a_acc / total)))
        rows.append(row)
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    jobs = [
        # apple-touch-icon musi byc pelnym kwadratem - iOS sam zaokragla narozniki
        ("icon-180.png", 180, 0.0, False),
        ("icon-192.png", 192, 0.0, False),
        ("icon-512.png", 512, 0.0, False),
        # maskowalna: znak w bezpiecznej strefie, bo Android przycina do kola
        ("icon-maskable-512.png", 512, 0.14, False),
        # favicon z zaokraglonymi naroznikami, zeby ladnie siedziala w karcie
        ("favicon-64.png", 64, 0.0, True),
    ]
    for name, size, inset, rounded in jobs:
        rows = render(size, inset, rounded)
        path = os.path.join(OUT, name)
        write_png(path, size, size, rows)
        print("%-26s %4dx%-4d %6.1f kB" % (name, size, size, os.path.getsize(path) / 1024))


if __name__ == "__main__":
    main()
