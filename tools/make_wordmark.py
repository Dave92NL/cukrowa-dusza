#!/usr/bin/env python3
"""Wycina sam napis "cukrowa dusza" z logo jako PNG z przezroczystoscia.

    python3 tools/make_wordmark.py

Po co: nazwa w aplikacji ma byc w tym samym pismie co logo, ale czcionka
Brittany Signature jest darmowa wylacznie do uzytku osobistego, a repozytorium
musi byc publiczne - osadzenie pliku czcionki byloby redystrybucja. Napis
w logo to grafika, do ktorej Dawid ma prawa, wiec bierzemy ja wprost.

Jak: zloto odroznia sie od wszystkich tel kanalem niebieskim (zloto B~32,
biel 224, krem 160, miska 192), a dodatkowa bramka R-B odcina szarosci.
Krycie liczone plynnie, zeby zachowac wygladzone krawedzie pisma.
Czysty Python - zlib i wlasny koder PNG, bez PIL.
"""
import os
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SRC = os.path.join(ROOT, "brand", "logo-zrodlo.png")
OUT = os.path.join(ROOT, "docs", "icons", "napis.png")

# Pasmo z napisem i wyciecie w poziomie tak, by pominac luki zlotego okregu.
BAND = (612, 852)
XCUT = (136, 1046)            # wewnatrz zlotego okregu, zeby nie zlapac jego lukow

B_FULL, B_NONE = 58, 150      # krycie 1.0 przy B<=58, 0.0 przy B>=150
RB_MIN = 75                   # krem ma R-B ~64, zloto ~128 - prog miedzy nimi
MIN_BLOB = 500                # mniejsze plamki to gwiazdki i smugi, nie litery
# Zlota obwodka to okrag o znanym srodku i promieniu - odcinamy ja geometria,
# a nie zgadywaniem prostokatow. Ogonki pisma mieszcza sie wewnatrz.
R_MAX = 470
INK = (168, 128, 31)          # #A8801F - zloto marki, czytelne na bieli


def decode_png(path):
    data = open(path, "rb").read()
    pos, idat, meta = 8, b"", None
    while pos < len(data):
        (ln,) = struct.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        if tag == b"IHDR":
            meta = struct.unpack(">IIBBBBB", chunk)
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break
        pos += 12 + ln
    w, h, depth, ctype = meta[0], meta[1], meta[2], meta[3]
    if depth != 8 or ctype not in (2, 6):
        sys.exit("Obslugiwane tylko 8-bitowe RGB/RGBA, dostalem depth=%s ctype=%s" % (depth, ctype))
    bpp = 3 if ctype == 2 else 4
    stride = w * bpp
    raw = zlib.decompress(idat)
    out = bytearray(w * h * bpp)
    prev = bytearray(stride)
    i = 0
    for y in range(h):
        f = raw[i]; i += 1
        line = bytearray(raw[i:i + stride]); i += stride
        if f == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((a + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, bpp, out


def encode_png(path, w, h, rows):
    raw = bytearray()
    for row in rows:
        raw.append(0)
        raw += row

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def main():
    if not os.path.exists(SRC):
        sys.exit("Brak %s" % SRC)
    w, h, bpp, px = decode_png(SRC)

    y0, y1 = BAND
    x0, x1 = XCUT
    cw, ch = x1 - x0, y1 - y0

    ccx = ccy = (w - 1) / 2.0
    r_max_sq = R_MAX * R_MAX

    alpha = [[0] * cw for _ in range(ch)]
    for yi, y in enumerate(range(y0, y1)):
        base = y * w * bpp
        row = alpha[yi]
        dy2 = (y - ccy) ** 2
        for xi, x in enumerate(range(x0, x1)):
            if (x - ccx) ** 2 + dy2 > r_max_sq:
                continue
            o = base + x * bpp
            r, g, b = px[o], px[o + 1], px[o + 2]
            if r - b < RB_MIN or g < b:
                continue
            if b >= B_NONE:
                continue
            a = 255 if b <= B_FULL else int(255 * (B_NONE - b) / (B_NONE - B_FULL))
            row[xi] = a

    # Usun drobiny: gwiazdki z logo i resztki rysunku zostaja jako male,
    # odosobnione plamy. Litery sa duze i spojne, wiec przezywaja filtr.
    seen = bytearray(cw * ch)
    for sy in range(ch):
        for sx in range(cw):
            if seen[sy * cw + sx] or alpha[sy][sx] <= 12:
                continue
            stack, blob = [(sx, sy)], []
            seen[sy * cw + sx] = 1
            while stack:
                x, y = stack.pop()
                blob.append((x, y))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < cw and 0 <= ny < ch and not seen[ny * cw + nx] \
                       and alpha[ny][nx] > 12:
                        seen[ny * cw + nx] = 1
                        stack.append((nx, ny))
            if len(blob) < MIN_BLOB:
                for x, y in blob:
                    alpha[y][x] = 0

    # Przytnij do faktycznej zawartosci, zeby nie ciagnac pustych marginesow.
    cols = [x for x in range(cw) if any(alpha[y][x] > 12 for y in range(ch))]
    rows_ = [y for y in range(ch) if any(alpha[y][x] > 12 for x in range(cw))]
    if not cols or not rows_:
        sys.exit("Nie znalazlem zlotych pikseli - sprawdz BAND/XCUT.")
    cx0, cx1 = cols[0], cols[-1] + 1
    cy0, cy1 = rows_[0], rows_[-1] + 1
    fw, fh = cx1 - cx0, cy1 - cy0

    out_rows = []
    for y in range(cy0, cy1):
        row = bytearray()
        for x in range(cx0, cx1):
            a = alpha[y][x]
            row += bytes((INK[0], INK[1], INK[2], a)) if a else b"\0\0\0\0"
        out_rows.append(row)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    encode_png(OUT, fw, fh, out_rows)
    covered = sum(1 for y in range(cy0, cy1) for x in range(cx0, cx1) if alpha[y][x] > 12)
    print("napis.png  %dx%d  %.1f kB  (%.1f%% powierzchni to pismo)"
          % (fw, fh, os.path.getsize(OUT) / 1024, covered / (fw * fh) * 100))


if __name__ == "__main__":
    main()
