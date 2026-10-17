#!/usr/bin/env python3
"""Szuka produktu w baktotaal.nl i podaje gotowy wpis do katalogu.

    python3 tools/find_baktotaal.py cakeboard rond 24
    python3 tools/find_baktotaal.py progel red --ceny
    python3 tools/find_baktotaal.py taartdoos --ceny --limit 5

Dlaczego nie uzywamy wyszukiwarki sklepu: robots.txt zabrania /catalogsearch/.
Szukamy wiec w sitemapie, ktora sklep publikuje wlasnie po to, zeby ja czytac.
Sitemapa jest cachowana lokalnie na dobe - to 16 MB, nie ma sensu pobierac jej
za kazdym razem.
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import baktotaal  # noqa: E402

CACHE = os.path.join(os.path.dirname(os.path.realpath(__file__)), ".sitemap-cache.txt")
CACHE_MAX_AGE = 24 * 3600


def urls(refresh=False):
    if not refresh and os.path.exists(CACHE) \
       and time.time() - os.path.getmtime(CACHE) < CACHE_MAX_AGE:
        with open(CACHE, encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip()]
    sys.stderr.write("Pobieram sitemape sklepu (raz na dobe)...\n")
    found = baktotaal.sitemap_urls()
    with open(CACHE, "w", encoding="utf-8") as f:
        f.write("\n".join(found) + "\n")
    return found


def slug_words(url):
    return url.rsplit("/", 1)[-1].replace("-", " ")


def main():
    ap = argparse.ArgumentParser(description="Szukaj produktu w baktotaal.nl")
    ap.add_argument("slowa", nargs="+", help="fragmenty nazwy, np. cakeboard rond 24")
    ap.add_argument("--ceny", action="store_true", help="pobierz ceny znalezionych produktow")
    ap.add_argument("--limit", type=int, default=12, help="ile wynikow pokazac")
    ap.add_argument("--odswiez", action="store_true", help="pobierz sitemape na nowo")
    args = ap.parse_args()

    terms = [w.lower() for w in args.slowa]
    hits = [u for u in urls(args.odswiez)
            if all(t in slug_words(u).lower() for t in terms)]

    if not hits:
        print("Nic nie znalazlem dla: %s" % " ".join(terms))
        print("Sprobuj mniej slow albo nazwy holenderskiej "
              "(taartdoos, cakeboard, kleurstof, rolfondant, spuitzak).")
        return 1

    print("Znaleziono %d, pokazuje %d:\n" % (len(hits), min(len(hits), args.limit)))
    for url in hits[:args.limit]:
        if not args.ceny:
            print("  %s" % url)
            continue
        try:
            r = baktotaal.product(url)
        except ValueError as e:
            print("  %-58s  BLAD: %s" % (slug_words(url)[:56], e))
            continue
        promo = "  PROMOCJA z %.2f" % (r["oldPrice"] / 100) if r["oldPrice"] else ""
        print("  %-52s %7.2f EUR%s" % ((r["title"] or "")[:50], r["price"] / 100, promo))
        print("    %s" % url)

    if args.ceny:
        print("\nZeby dodac do katalogu, dopisz w docs/data/catalog.json:")
        print('  "moj_klucz": { "name": "Nazwa po polsku", "source": "baktotaal",')
        print('                 "pack": 1, "unit": "szt",')
        print('                 "url": "<adres z gory>" },')
        print("\n'pack' to zawartosc opakowania w jednostce bazowej (g, ml, szt).")
        print("To TY jestes zrodlem prawdy dla gramatury - synchronizacja zmienia tylko cene.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
