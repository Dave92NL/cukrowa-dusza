#!/usr/bin/env python3
"""Odczyt cen ze sklepu baktotaal.nl (podklady, barwniki, opakowania, dekoracje).

Inaczej niz Albert Heijn: baktotaal nie ma ochrony antybotowej, a robots.txt
pozwala na strony produktow. Wystarczy zwykly GET, bez posrednika.

Czego ten modul NIE robi: nie dotyka /catalogsearch/ ani adresow z filtrami,
bo robots.txt ich zabrania. Produkty pinujemy adresem strony, a szukamy ich
w sitemapie, ktora sklep publikuje wlasnie w tym celu.

CENA BRUTTO, NIE NETTO - to najwazniejsza decyzja w tym pliku.
Dane strukturalne JSON-LD sa na tym sklepie niespojne: dla prostego produktu
podaja cene brutto (sprinkles 6,99 = 6,99), ale dla wariantu produktu
zlozonego netto (cakeboard 1,31 przy wyswietlanych 1,59 = +21% VAT).
Branie JSON-LD wprost zanizaloby koszt podkladu o jedna piata. Dlatego cene
bierzemy z `data-price-amount` glownego produktu - czyli dokladnie z tej
liczby, ktora sklep pokazuje na stronie i ktora placisz przy kasie.
"""
import json
import re
import urllib.error
import urllib.request

BASE = "https://www.baktotaal.nl"
SITEMAP_INDEX = BASE + "/sitemap/store_b2c_dutch/sitemap.xml"
UA = "cukrowa-dusza-price-sync/1.0 (osobisty kalkulator kosztow tortow)"
TIMEOUT = 30


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml",
        "Accept-Language": "nl,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        charset = r.headers.get_content_charset() or "utf-8"
        return r.read().decode(charset, "replace")


def _ld_blocks(html):
    for raw in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(raw.strip())
        except ValueError:
            continue
        for item in (data if isinstance(data, list) else [data]):
            if isinstance(item, dict):
                yield item


def _main_product_id(html):
    """Pierwszy <input name="product"> to glowny produkt strony.

    Strona zawiera takze polecane produkty z wlasnymi cenami, wiec bez tego
    kotwiczenia latwo odczytac cene zupelnie innego towaru.
    """
    m = re.search(r'<input[^>]*name="product"[^>]*value="(\d+)"', html)
    return m.group(1) if m else None


def _price_from_box(html, pid):
    """(brutto, cena_przed_promocja) z widgetu ceny glownego produktu."""
    box = re.search(r'data-price-box="product-id-%s"(.{0,4000}?)</div>\s*</div>' % re.escape(pid),
                    html, re.S)
    blob = box.group(1) if box else ""

    def grab(kind):
        m = (re.search(r'data-price-type="%s"[^>]*data-price-amount="([\d.]+)"' % kind, blob)
             or re.search(r'data-price-amount="([\d.]+)"[^>]*data-price-type="%s"' % kind, blob))
        return round(float(m.group(1)), 2) if m else None

    return grab("finalPrice"), grab("oldPrice")


def _title(html):
    m = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]+)"', html)
    if m:
        return m.group(1).strip()
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def parse_product(html):
    """Zwraca slownik z cena brutto w groszach albo podnosi ValueError.

    Nigdy nie zwraca ceny, co do ktorej nie ma pewnosci - brak ceny jest
    lepszy niz cena innego produktu albo netto wziete za brutto.
    """
    pid = _main_product_id(html)
    if not pid:
        raise ValueError("nie znalazlem glownego produktu na stronie")

    gross, old = _price_from_box(html, pid)
    if gross is None:
        raise ValueError("strona nie podaje ceny (produkt wycofany?)")

    name = sku = ean = avail = None
    net = None
    for item in _ld_blocks(html):
        t = item.get("@type")
        if t == "Product":
            offers = item.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            name = item.get("name") or name
            sku = item.get("sku") or sku
            ean = item.get("gtin13") or item.get("gtin") or ean
            avail = (offers.get("availability") or "").rsplit("/", 1)[-1] or avail
            try:
                net = float(offers.get("price"))
            except (TypeError, ValueError):
                pass
        elif t == "ProductGroup":
            name = name or item.get("name")
            # Wariant dopasowujemy po cenie: netto * VAT ~ brutto. Dzieki temu
            # dostajemy SKU i stawke VAT bez zgadywania kategorii produktu.
            for v in (item.get("hasVariant") or []):
                offers = v.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                try:
                    p = float(offers.get("price"))
                except (TypeError, ValueError):
                    continue
                for rate in (1.21, 1.09, 1.00):
                    if abs(p * rate - gross) < 0.02:
                        sku = sku or v.get("sku")
                        ean = ean or v.get("gtin13")
                        net = p
                        break

    # Netto zapisujemy TYLKO wtedy, gdy mamy pewnosc, ze JSON-LD podal netto -
    # czyli gdy stosunek do ceny wyswietlanej to rozpoznawalna stawka VAT.
    # Stosunek 1,00 nie znaczy "zero VAT", tylko "JSON-LD juz podal brutto",
    # a wtedy stawki nie da sie z tej strony wyczytac. Pole, ktore znaczy dwie
    # rozne rzeczy, predzej czy pozniej zostanie zle uzyte - wiec zostaje puste.
    vat = net_cents = None
    if net and gross and net > 0:
        ratio = gross / net
        for cand in (1.09, 1.21):
            if abs(ratio - cand) < 0.01:
                vat, net_cents = cand, int(round(net * 100))
                break

    return {
        "title": (name or _title(html) or "").strip() or None,
        "price": int(round(gross * 100)),          # brutto - tyle placisz
        "netPrice": net_cents,                     # netto, gdy dalo sie ustalic
        "vatRate": vat,                            # 1.09 lub 1.21, inaczej None
        "oldPrice": int(round(old * 100)) if old and old > gross else None,
        "sku": sku,
        "ean": ean,
        "inStock": None if avail is None else (avail == "InStock"),
    }


def product(url):
    """Pobiera i parsuje strone produktu. Podnosi ValueError z czytelnym powodem."""
    if not url.startswith(BASE):
        raise ValueError("adres spoza baktotaal.nl: %s" % url)
    if "/catalogsearch/" in url or "?" in url:
        raise ValueError("robots.txt zabrania wyszukiwarki i adresow z filtrami")
    try:
        html = fetch(url)
    except urllib.error.HTTPError as e:
        raise ValueError("HTTP %s" % e.code)
    except Exception as e:                                   # noqa: BLE001
        raise ValueError(str(e))
    return parse_product(html)


def sitemap_urls():
    """Adresy produktow z sitemapy sklepu - jedyny dozwolony sposob szukania."""
    index = fetch(SITEMAP_INDEX)
    out = []
    for sm in re.findall(r"<loc>([^<]+)</loc>", index):
        for loc in re.findall(r"<loc>([^<]+)</loc>", fetch(sm)):
            # strony produktow maja plaski adres, kategorie zawieraja ukosnik
            rest = loc[len(BASE):].strip("/")
            if rest and "/" not in rest:
                out.append(loc)
    return out
