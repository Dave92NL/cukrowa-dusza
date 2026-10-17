#!/usr/bin/env python3
"""Pobiera ceny skladnikow z Albert Heijn i zapisuje docs/data/prices.json.

Dlaczego przez Apify, a nie wprost z api.ah.nl:
AH stoi za Akamai Bot Manager. Sprawdzone na zywo - zapytanie z curla dostaje
503 (odrzut po fingerprincie TLS), a z przegladarki nie przechodzi, bo api.ah.nl
nie wysyla naglowkow CORS dla obcych originow. Aktor Apify utrzymuje obejscie
po swojej stronie, wiec to jego problem, nie nasz.

Aktor nie potrafi szukac po webshopId, ale potrafi po kodzie EAN - dlatego
skladniki pinujemy do EAN z opakowania (patrz docs/data/catalog.json).

Uzycie:
    export APIFY_TOKEN=apify_api_...
    python3 tools/sync_prices.py --dry-run      # pokaz roznice, nie zapisuj
    python3 tools/sync_prices.py                # zapisz
    python3 tools/sync_prices.py --only maslo   # tylko wybrane skladniki

Zasada nadrzedna: nigdy nie podstawiaj po cichu ceny, ktorej nie jestes pewien.
Od tej liczby zalezy cena, po ktorej sprzedawany jest tort.
"""

import argparse
import concurrent.futures as futures
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ACTOR = "studio-amba~albert-heijn-scraper"
API = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"
ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
CATALOG = os.path.join(ROOT, "docs", "data", "catalog.json")
PRICES = os.path.join(ROOT, "docs", "data", "prices.json")

# Skok ceny powyzej tego progu traktujemy jako podmiane produktu, nie przecene.
JUMP_LIMIT = 0.40
TIMEOUT = 180
WORKERS = 4


# ───────────────────────── pomocnicze ─────────────────────────

def cents(value):
    """Cena z Apify (float w euro) -> grosze jako int."""
    if value is None:
        return None
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return None


UNIT_RE = re.compile(
    r"(?:(?P<mult>\d+)\s*[x×]\s*)?(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>kg|g|gram|l|liter|ltr|ml|cl|stuks|stuk|st)\b",
    re.I,
)
TO_BASE = {"kg": (1000, "g"), "g": (1, "g"), "gram": (1, "g"),
           "l": (1000, "ml"), "liter": (1000, "ml"), "ltr": (1000, "ml"),
           "ml": (1, "ml"), "cl": (10, "ml"),
           "stuks": (1, "szt"), "stuk": (1, "szt"), "st": (1, "szt")}


def parse_unit(text):
    """'250 g' -> (250,'g');  '1 kg' -> (1000,'g');  '6 x 125 g' -> (750,'g').

    Sluzy wylacznie do WYKRYCIA niezgodnosci z katalogiem. Gramatura w katalogu
    pozostaje zrodlem prawdy, bo tekst z AH jest nieregularny.
    """
    if not text:
        return None
    m = UNIT_RE.search(str(text))
    if not m:
        return None
    factor, base = TO_BASE[m.group("unit").lower()]
    amount = float(m.group("num").replace(",", ".")) * factor
    if m.group("mult"):
        amount *= int(m.group("mult"))
    return (round(amount, 3), base)


def apify_run(token, query, fetch_details):
    """Jeden przebieg aktora. Zwraca liste pozycji datasetu."""
    url = API.format(actor=ACTOR) + "?token=" + urllib.parse.quote(token)
    body = json.dumps({
        "searchQuery": str(query),
        "maxResults": 5,
        "fetchDetails": bool(fetch_details),
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode() or "[]")


def pick(items, entry):
    """Wybiera wlasciwy produkt z wynikow. Zwraca (produkt, zweryfikowany, powod)."""
    if not items:
        return None, False, "brak wynikow w AH"

    ean = str(entry["ean"]).strip() if entry.get("ean") else None
    sku = str(entry["sku"]).strip() if entry.get("sku") else None

    if ean:
        for it in items:
            if it.get("ean") and str(it["ean"]).strip() == ean:
                return it, True, None
        # Szukalismy po EAN, wiec pierwszy wynik to prawie pewnie on,
        # ale bez fetchDetails nie mamy czym tego potwierdzic.
        return items[0], False, "EAN nie potwierdzony w odpowiedzi"

    if sku:
        for it in items:
            if it.get("sku") and str(it["sku"]).strip() == sku:
                return it, True, None
        return None, False, "produkt o podanym sku nie znalezniony"

    return items[0], False, "dopasowanie tylko po nazwie - potwierdz produkt"


def fetch_one(token, key, entry):
    """Zwraca (key, wpis do prices.json)."""
    query = entry.get("ean") or entry.get("query")
    if not query:
        return key, {"ok": False, "warning": "brak 'ean' i 'query' w katalogu"}

    try:
        items = apify_run(token, query, fetch_details=bool(entry.get("ean")))
    except urllib.error.HTTPError as e:
        return key, {"ok": False, "warning": "Apify HTTP %s: %s" % (e.code, e.reason)}
    except Exception as e:                                   # noqa: BLE001
        return key, {"ok": False, "warning": "Apify blad: %s" % e}

    item, verified, reason = pick(items, entry)
    if item is None:
        return key, {"ok": False, "warning": reason}

    price = cents(item.get("price"))
    if price is None or price <= 0:
        return key, {"ok": False, "warning": "brak ceny w odpowiedzi"}

    rec = {
        "title": " ".join(x for x in [item.get("brand"), item.get("name")] if x) or item.get("name"),
        "price": price,
        "bonusPrice": cents(item.get("promotionPrice")),
        "bonusLabel": item.get("bonusMechanism") or None,
        "bonusUntil": item.get("promotionEndDate") or None,
        "sku": item.get("sku"),
        "ean": item.get("ean"),
        "url": item.get("url"),
        "scrapedUnit": item.get("unit"),
        "inStock": item.get("inStock"),
        "ok": True,
    }
    if not verified:
        rec["ok"] = False
        rec["warning"] = reason

    # Promocja drozsza od ceny podstawowej = blad w danych, nie promocja.
    if rec["bonusPrice"] is not None and rec["bonusPrice"] >= price:
        rec["bonusPrice"] = None
        rec["bonusLabel"] = None

    # Czy AH nie zmienil wielkosci opakowania pod tym samym produktem.
    declared = (float(entry["pack"]), entry["unit"])
    scraped = parse_unit(item.get("unit"))
    if scraped and scraped[1] == declared[1] and abs(scraped[0] - declared[0]) > 0.01:
        rec["ok"] = False
        rec["warning"] = "opakowanie w AH to %g %s, w katalogu %g %s - popraw 'pack'" % (
            scraped[0], scraped[1], declared[0], declared[1])

    return key, rec


# ───────────────────────── glowny przebieg ─────────────────────────

def load(path, fallback):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return fallback


def main():
    ap = argparse.ArgumentParser(description="Synchronizacja cen AH -> prices.json")
    ap.add_argument("--dry-run", action="store_true", help="pokaz roznice, nie zapisuj")
    ap.add_argument("--only", nargs="*", metavar="KLUCZ", help="tylko te skladniki")
    args = ap.parse_args()

    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        sys.exit("APIFY_TOKEN nie ustawiony. Token znajdziesz w Apify -> Settings -> Integrations.")

    catalog = load(CATALOG, None)
    if not catalog:
        sys.exit("Nie moge odczytac %s" % CATALOG)
    previous = load(PRICES, {"products": {}})
    prev_products = previous.get("products", {})

    targets = {k: v for k, v in catalog.items()
               if not k.startswith("_") and not v.get("manual")}
    if args.only:
        unknown = [k for k in args.only if k not in targets]
        if unknown:
            sys.exit("Nieznane skladniki: %s" % ", ".join(unknown))
        targets = {k: targets[k] for k in args.only}

    if not targets:
        sys.exit("Katalog nie zawiera skladnikow do synchronizacji.")

    print("Pobieram %d skladnikow przez Apify (%s)...\n" % (len(targets), ACTOR))
    results = {}
    with futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        jobs = [pool.submit(fetch_one, token, k, v) for k, v in sorted(targets.items())]
        for job in futures.as_completed(jobs):
            key, rec = job.result()
            results[key] = rec

    # ── zabezpieczenia: stara cena jest lepsza niz zla cena ──
    ok_count = sum(1 for r in results.values() if r.get("ok"))
    if ok_count == 0:
        sys.exit("\nBLAD: zadna cena nie zostala pobrana. Nie nadpisuje %s." % os.path.basename(PRICES))

    products, changes, warnings = {}, [], []
    for key in sorted(set(list(prev_products) + list(results))):
        old = prev_products.get(key)
        new = results.get(key)

        if new is None:                       # nie bylo w tym przebiegu (--only)
            if old:
                products[key] = old
            continue

        if not new.get("ok"):
            warnings.append((key, new.get("warning", "nieznany blad")))
            if old and old.get("price"):      # zachowaj ostatnia znana cene
                kept = dict(old)
                kept["ok"] = False
                kept["warning"] = new.get("warning")
                kept["stale"] = True
                products[key] = kept
            else:
                products[key] = new
            continue

        # Skok ceny ponad prog traktujemy jako podmiane produktu.
        if old and old.get("price") and old.get("ok") is not False:
            delta = abs(new["price"] - old["price"]) / old["price"]
            if delta > JUMP_LIMIT:
                warnings.append((key, "cena %s -> %s (%.0f%%) - odrzucona jako podejrzana" % (
                    old["price"] / 100, new["price"] / 100, delta * 100)))
                kept = dict(old)
                kept["ok"] = False
                kept["warning"] = "podejrzany skok ceny do %.2f EUR - sprawdz produkt" % (new["price"] / 100)
                kept["stale"] = True
                products[key] = kept
                continue
            if new["price"] != old["price"]:
                changes.append((key, old["price"], new["price"]))
        elif not old:
            changes.append((key, None, new["price"]))

        products[key] = new

    out = {
        "syncedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "apify/" + ACTOR,
        "products": products,
    }

    # ── raport ──
    if changes:
        print("Zmiany cen:")
        for key, old, new in changes:
            print("  %-14s %s -> %6.2f EUR" % (
                key, ("  nowy " if old is None else "%6.2f" % (old / 100)), new / 100))
    else:
        print("Zmian cen: brak.")

    bonuses = [(k, v) for k, v in products.items() if v.get("bonusPrice")]
    if bonuses:
        print("\nW promocji Bonus:")
        for key, v in sorted(bonuses):
            print("  %-14s %6.2f -> %6.2f EUR  %s" % (
                key, v["price"] / 100, v["bonusPrice"] / 100, v.get("bonusLabel") or ""))

    if warnings:
        print("\nOSTRZEZENIA (stare ceny zachowane, oznaczone jako niesweze):")
        for key, msg in sorted(warnings):
            print("  %-14s %s" % (key, msg))

    print("\nPobrano poprawnie %d z %d." % (ok_count, len(targets)))

    if args.dry_run:
        print("--dry-run: nic nie zapisano.")
        return 0

    with open(PRICES, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
    print("Zapisano %s" % PRICES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
