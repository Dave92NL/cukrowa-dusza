#!/usr/bin/env python3
"""Wypisuje klucze katalogu dla danego zrodla, oddzielone spacja.

    python3 tools/catalog_keys.py baktotaal

Uzywane przez workflow, gdy brakuje tokenu Apify: pozwala pobrac same ceny
z baktotaal.nl zamiast przerywac caly przebieg. Osobny plik, a nie python3 -c
w YAML - wklejony tam kod ma wciecie bloku i wywala sie na IndentationError.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CATALOG = os.path.join(ROOT, "docs", "data", "catalog.json")


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else "baktotaal"
    with open(CATALOG, encoding="utf-8") as f:
        catalog = json.load(f)
    keys = []
    for key, entry in catalog.items():
        if key.startswith("_"):
            continue
        src = entry.get("source") or ("manual" if entry.get("manual") else "ah")
        if src == want:
            keys.append(key)
    print(" ".join(sorted(keys)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
