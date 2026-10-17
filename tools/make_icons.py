#!/usr/bin/env python3
"""Generuje ikony PWA z logo marki.

    python3 tools/make_icons.py

Zrodlo: brand/logo-zrodlo.png (1181x1181, logo "cukrowa dusza").
Uzywa `sips`, ktory jest wbudowany w macOS - nic nie trzeba instalowac.
Ikony sa commitowane do repo, wiec skrypt nie musi dzialac na Linuksie w CI.

Dwa warianty, bo systemy maskuja ikony inaczej:
  any       - logo przyciete do zlotego okregu, wypelnia kafelek.
              iOS sam zaokragla narozniki, wiec oddajemy pelny kwadrat.
  maskable  - to samo, ale wpisane w 80% powierzchni na bialym tle,
              bo Android potrafi przyciac ikone do kola i zjadlby zlota obwodke.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SRC = os.path.join(ROOT, "brand", "logo-zrodlo.png")
OUT = os.path.join(ROOT, "docs", "icons")

# Bialy margines wokol zlotego okregu w pliku zrodlowym (px z kazdej strony).
TRIM = 90
# Udzial rysunku w ikonie maskowalnej - reszta to bezpieczny margines.
SAFE = 0.80


def sips(*args):
    r = subprocess.run(["sips", *args], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("sips nie powiodl sie: %s" % (r.stderr.strip() or r.stdout.strip()))
    return r


def dimensions(path):
    out = sips("-g", "pixelWidth", "-g", "pixelHeight", path).stdout
    vals = {}
    for line in out.splitlines():
        if ":" in line:
            k, v = line.rsplit(":", 1)
            vals[k.strip()] = v.strip()
    return int(vals["pixelWidth"]), int(vals["pixelHeight"])


def main():
    if not os.path.exists(SRC):
        sys.exit("Brak pliku zrodlowego: %s" % SRC)
    if not shutil.which("sips"):
        sys.exit("Brak `sips` - ten skrypt dziala na macOS. Ikony sa juz w repo.")

    os.makedirs(OUT, exist_ok=True)
    w, h = dimensions(SRC)
    side = min(w, h) - 2 * TRIM
    print("zrodlo %dx%d, przycinam do %dx%d (margines %d px)\n" % (w, h, side, side, TRIM))

    with tempfile.TemporaryDirectory() as tmp:
        circle = os.path.join(tmp, "circle.png")
        sips("-c", str(side), str(side), "--cropOffset", str(TRIM), str(TRIM),
             SRC, "--out", circle)

        for name, size in [("icon-180.png", 180), ("icon-192.png", 192),
                           ("icon-512.png", 512), ("favicon-64.png", 64)]:
            path = os.path.join(OUT, name)
            sips("-s", "format", "png", "-z", str(size), str(size), circle, "--out", path)
            print("%-24s %4dx%-4d %6.1f kB" % (name, size, size, os.path.getsize(path) / 1024))

        # maskowalna: rysunek na 80%, reszta bialy margines
        inner = round(512 * SAFE)
        small = os.path.join(tmp, "small.png")
        sips("-s", "format", "png", "-z", str(inner), str(inner), circle, "--out", small)
        # padToHeightWidth dokleja tlo dookola; bialy pasuje do logo
        masked = os.path.join(OUT, "icon-maskable-512.png")
        sips("-p", "512", "512", "--padColor", "FFFFFF", small, "--out", masked)
        print("%-24s %4dx%-4d %6.1f kB" % ("icon-maskable-512.png", 512, 512,
                                           os.path.getsize(masked) / 1024))

    print("\nGotowe. Ikony sa commitowane razem z kodem.")


if __name__ == "__main__":
    main()
