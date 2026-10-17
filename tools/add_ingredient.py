#!/usr/bin/env python3
"""Dodaje (albo poprawia) skladnik w docs/data/catalog.json.

    python3 tools/add_ingredient.py --zrodlo baktotaal --klucz podklad_25 \
        --nazwa "Podklad Ø25 cm" --pack 1 --unit szt \
        --wartosc https://www.baktotaal.nl/cakeboard-zilver-rond-o25cm

    python3 tools/add_ingredient.py --zrodlo ah --klucz migdaly \
        --nazwa "Platki migdalowe" --pack 100 --unit g --wartosc "ah amandelschaafsel"

Uzywane przez workflow, gdy aplikacja zglosi nowy produkt z telefonu.
Sprawdza wpis ZANIM trafi do katalogu - zly wpis zepsulby synchronizacje
wszystkich pozostalych skladnikow, wiec lepiej odrzucic go tutaj.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import baktotaal  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CATALOG = os.path.join(ROOT, "docs", "data", "catalog.json")

KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
UNITS = ("g", "ml", "szt")


def main():
    ap = argparse.ArgumentParser(description="Dodaj skladnik do katalogu")
    ap.add_argument("--zrodlo", required=True, choices=("ah", "baktotaal", "manual"))
    ap.add_argument("--klucz", required=True, help="identyfikator, np. podklad_25")
    ap.add_argument("--nazwa", required=True, help="nazwa po polsku")
    ap.add_argument("--pack", required=True, type=float, help="zawartosc opakowania")
    ap.add_argument("--unit", required=True, choices=UNITS)
    ap.add_argument("--wartosc", default="", help="EAN lub nazwa (ah) / adres strony (baktotaal)")
    ap.add_argument("--cena", default="", help="cena w EUR, tylko dla zrodla manual")
    args = ap.parse_args()

    key = args.klucz.strip().lower()
    if not KEY_RE.match(key):
        sys.exit("Zly klucz '%s'. Dozwolone: male litery, cyfry i podkreslenie, 2-40 znakow."
                 % args.klucz)

    nazwa = args.nazwa.strip()
    if not nazwa:
        sys.exit("Nazwa nie moze byc pusta.")

    if args.pack <= 0:
        sys.exit("Zawartosc opakowania musi byc wieksza od zera.")
    pack = int(args.pack) if float(args.pack).is_integer() else args.pack

    entry = {"name": nazwa, "source": args.zrodlo, "pack": pack, "unit": args.unit}
    wartosc = args.wartosc.strip()

    if args.zrodlo == "baktotaal":
        if not wartosc:
            sys.exit("Dla baktotaal podaj --wartosc z adresem strony produktu.")
        # Sprawdzamy od razu, czy strona da sie odczytac. Lepiej odrzucic teraz,
        # niz wpuscic do katalogu wpis, ktory bedzie sie wywalal co noc.
        try:
            r = baktotaal.product(wartosc)
        except ValueError as e:
            sys.exit("Nie moge odczytac tej strony: %s" % e)
        entry["url"] = wartosc
        print("Sprawdzone: %s -> %.2f EUR" % (r["title"], r["price"] / 100))

    elif args.zrodlo == "ah":
        if not wartosc:
            sys.exit("Dla Albert Heijn podaj --wartosc: kod EAN albo nazwe do wyszukania.")
        digits = re.sub(r"\D", "", wartosc)
        if digits == wartosc and 8 <= len(digits) <= 14:
            entry["ean"] = digits
            print("Pinuje po kodzie EAN: %s" % digits)
        else:
            entry["query"] = wartosc
            print("Pinuje po nazwie: %s" % wartosc)
            print("Wynik bedzie oznaczony jako niepotwierdzony, dopoki nie dopiszesz 'ean'.")

    else:  # manual
        cena = args.cena.replace(",", ".").strip()
        try:
            grosze = int(round(float(cena) * 100))
        except ValueError:
            sys.exit("Dla zrodla manual podaj --cena, np. 3.49")
        if grosze <= 0:
            sys.exit("Cena musi byc wieksza od zera.")
        entry["price"] = grosze
        print("Cena reczna: %.2f EUR" % (grosze / 100))

    with open(CATALOG, encoding="utf-8") as f:
        catalog = json.load(f)

    istnial = key in catalog
    catalog[key] = entry
    with open(CATALOG, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("%s '%s' w katalogu (%s, %g %s)."
          % ("Zaktualizowano" if istnial else "Dodano", key, args.zrodlo, pack, args.unit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
