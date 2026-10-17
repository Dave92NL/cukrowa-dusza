#!/usr/bin/env python3
"""Testy czesci pythonowej. Biblioteka standardowa, zero zaleznosci.

    python3 tools/test_sync.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sync_prices as sp  # noqa: E402
import baktotaal as bt  # noqa: E402


class TestCents(unittest.TestCase):
    def test_euro_na_grosze(self):
        self.assertEqual(sp.cents(2.79), 279)
        self.assertEqual(sp.cents(1), 100)
        self.assertEqual(sp.cents(0.85), 85)

    def test_zaokraglanie_floatow(self):
        # 2.675 * 100 to w binarnym 267.49999..., musi wyjsc 268
        self.assertEqual(sp.cents(2.675), 268)
        self.assertEqual(sp.cents(10.955), 1096)

    def test_brak_wartosci(self):
        self.assertIsNone(sp.cents(None))
        self.assertIsNone(sp.cents("nie liczba"))


class TestParseUnit(unittest.TestCase):
    def test_gramy_i_kilogramy(self):
        self.assertEqual(sp.parse_unit("250 g"), (250.0, "g"))
        self.assertEqual(sp.parse_unit("1 kg"), (1000.0, "g"))
        self.assertEqual(sp.parse_unit("1,5 kg"), (1500.0, "g"))

    def test_plyny(self):
        self.assertEqual(sp.parse_unit("500 ml"), (500.0, "ml"))
        self.assertEqual(sp.parse_unit("1 l"), (1000.0, "ml"))
        self.assertEqual(sp.parse_unit("20 cl"), (200.0, "ml"))

    def test_sztuki(self):
        self.assertEqual(sp.parse_unit("10 stuks"), (10.0, "szt"))
        self.assertEqual(sp.parse_unit("1 stuk"), (1.0, "szt"))

    def test_wielopak(self):
        self.assertEqual(sp.parse_unit("6 x 125 g"), (750.0, "g"))
        self.assertEqual(sp.parse_unit("4 × 100 ml"), (400.0, "ml"))

    def test_nieczytelne(self):
        self.assertIsNone(sp.parse_unit(""))
        self.assertIsNone(sp.parse_unit(None))
        self.assertIsNone(sp.parse_unit("per stuk"))


class TestPick(unittest.TestCase):
    """Wybor produktu z wynikow - tu rodzi sie ryzyko zlej ceny."""

    A = {"sku": "wi111", "ean": "8710400000001", "name": "Roomboter", "price": 2.79}
    B = {"sku": "wi222", "ean": "8710400000002", "name": "Halvarine", "price": 1.19}

    def test_ean_dopasowany_jest_zweryfikowany(self):
        item, verified, _ = sp.pick([self.B, self.A], {"ean": "8710400000001"})
        self.assertEqual(item["sku"], "wi111")
        self.assertTrue(verified)

    def test_ean_bez_potwierdzenia_nie_jest_zweryfikowany(self):
        item, verified, reason = sp.pick(
            [{"sku": "wi111", "name": "Roomboter", "price": 2.79}], {"ean": "8710400000001"})
        self.assertFalse(verified)
        self.assertIn("EAN", reason)

    def test_sku_niedopasowane_odrzuca_produkt(self):
        item, verified, reason = sp.pick([self.B], {"query": "roomboter", "sku": "wi111"})
        self.assertIsNone(item)          # lepiej nic niz zly produkt
        self.assertFalse(verified)

    def test_tylko_nazwa_daje_niepotwierdzony(self):
        item, verified, reason = sp.pick([self.A, self.B], {"query": "roomboter"})
        self.assertEqual(item["sku"], "wi111")
        self.assertFalse(verified)
        self.assertIn("nazwie", reason)

    def test_brak_wynikow(self):
        item, verified, reason = sp.pick([], {"ean": "8710400000001"})
        self.assertIsNone(item)
        self.assertIn("brak", reason.lower())


class TestProgSkokuCeny(unittest.TestCase):
    def test_prog_odrzuca_podmiane_produktu(self):
        # 2,79 -> 5,49 to +97%, czyli prawie pewnie inny produkt
        self.assertGreater(abs(549 - 279) / 279, sp.JUMP_LIMIT)

    def test_prog_przepuszcza_normalna_podwyzke(self):
        # 2,79 -> 2,99 to +7%, zwykla zmiana polkowa
        self.assertLess(abs(299 - 279) / 279, sp.JUMP_LIMIT)

    def test_prog_przepuszcza_typowy_bonus(self):
        # -25% musi przejsc, bo Bonusy sa normalne
        self.assertLess(abs(164 - 219) / 219, sp.JUMP_LIMIT)


class TestKatalog(unittest.TestCase):
    """Katalog i ceny musza byc spojne - to samo sprawdza tests.html."""

    @classmethod
    def setUpClass(cls):
        import json
        with open(sp.CATALOG, encoding="utf-8") as f:
            cls.catalog = json.load(f)
        with open(sp.PRICES, encoding="utf-8") as f:
            cls.prices = json.load(f)
        cls.items = {k: v for k, v in cls.catalog.items() if not k.startswith("_")}

    def test_kazdy_wpis_ma_gramature_i_jednostke(self):
        for key, v in self.items.items():
            self.assertIn(v.get("unit"), ("g", "ml", "szt"), key)
            self.assertIsInstance(v.get("pack"), int, key)
            self.assertGreater(v["pack"], 0, key)

    def test_kazdy_wpis_da_sie_zsynchronizowac(self):
        for key, v in self.items.items():
            src = sp.source_of(v)
            self.assertIn(src, ("ah", "baktotaal", "manual"), key)
            if src == "manual":
                self.assertIsInstance(v.get("price"), int, key)
            elif src == "ah":
                self.assertTrue(v.get("ean") or v.get("query"),
                                "%s (ah) nie ma ani 'ean', ani 'query'" % key)
            else:
                url = v.get("url") or ""
                self.assertTrue(url.startswith(bt.BASE), "%s (baktotaal) nie ma 'url'" % key)
                self.assertNotIn("?", url, "%s: adres z filtrami, robots.txt tego zabrania" % key)
                self.assertNotIn("/catalogsearch/", url, key)

    def test_source_of_rozumie_stary_zapis(self):
        self.assertEqual(sp.source_of({"manual": True}), "manual")
        self.assertEqual(sp.source_of({}), "ah")
        self.assertEqual(sp.source_of({"source": "baktotaal"}), "baktotaal")

    def test_ceny_sa_calkowite_w_groszach(self):
        for key, v in self.prices["products"].items():
            self.assertIsInstance(v["price"], int, key)
            if v.get("bonusPrice") is not None:
                self.assertIsInstance(v["bonusPrice"], int, key)
                self.assertLess(v["bonusPrice"], v["price"], key)


# Strony baktotaal w dwoch ksztaltach, jakie sklep naprawde zwraca.
# Skrocone do tego, co czyta parser - testy maja byc offline i powtarzalne,
# zeby CI nie padalo przez chwilowa niedostepnosc sklepu.

PROSTY = """
<input type="hidden" name="product" value="31870" />
<div class="price-box" data-price-box="product-id-31870">
  <span data-price-type="finalPrice" data-price-amount="6.986901"></span>
</div></div>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Sprinkles World of Magic 90g",
 "sku":"BS0729","gtin13":"4252022407299",
 "offers":{"@type":"Offer","price":"6.99","priceCurrency":"EUR",
           "availability":"https://schema.org/InStock"}}
</script>
"""

WARIANT = """
<input type="hidden" name="product" value="1894" />
<div class="price-box" data-price-box="product-id-1894">
  <span data-price-type="finalPrice" data-price-amount="1.585101"></span>
</div></div>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"ProductGroup","name":"Cakeboard Zilver Rond",
 "hasVariant":[
   {"@type":"Product","name":"Ø15cm","sku":"CC106","offers":{"price":"0.98","priceCurrency":"EUR"}},
   {"@type":"Product","name":"Ø20cm","sku":"CC108","offers":{"price":"1.31","priceCurrency":"EUR"}}]}
</script>
"""

PROMOCJA = """
<input type="hidden" name="product" value="42" />
<div class="price-box" data-price-box="product-id-42">
  <span data-price-type="oldPrice" data-price-amount="10.00"></span>
  <span data-price-type="finalPrice" data-price-amount="7.50"></span>
</div></div>
"""


class TestBaktotaal(unittest.TestCase):
    """Najwazniejszy test w tym pliku: cena ma byc BRUTTO, zawsze.

    Sklep podaje w JSON-LD raz brutto (prosty produkt), raz netto (wariant).
    Pomylka to zanizenie kosztu podkladu o 21% i tort sprzedany za tanio.
    """

    def test_prosty_produkt_bierze_cene_wyswietlana(self):
        r = bt.parse_product(PROSTY)
        self.assertEqual(r["price"], 699)
        self.assertEqual(r["sku"], "BS0729")
        self.assertEqual(r["ean"], "4252022407299")
        self.assertTrue(r["inStock"])

    def test_wariant_NIE_bierze_netto_z_json_ld(self):
        r = bt.parse_product(WARIANT)
        self.assertEqual(r["price"], 159, "wzieta cena netto zamiast brutto")
        self.assertNotEqual(r["price"], 131)

    def test_wariant_dopasowany_po_cenie_daje_sku_i_vat(self):
        r = bt.parse_product(WARIANT)
        self.assertEqual(r["sku"], "CC108")       # Ø20cm, nie Ø15cm
        self.assertEqual(r["netPrice"], 131)
        self.assertAlmostEqual(r["vatRate"], 1.21, places=2)

    def test_netto_puste_gdy_stawki_nie_da_sie_ustalic(self):
        # Prosty produkt: JSON-LD juz podal brutto, wiec stawki nie znamy.
        # Pole ma zostac puste, a nie udawac zerowy VAT.
        r = bt.parse_product(PROSTY)
        self.assertIsNone(r["netPrice"])
        self.assertIsNone(r["vatRate"])

    def test_promocja_rozpoznana(self):
        r = bt.parse_product(PROMOCJA)
        self.assertEqual(r["price"], 750)
        self.assertEqual(r["oldPrice"], 1000)

    def test_brak_ceny_podnosi_blad_zamiast_zgadywac(self):
        with self.assertRaises(ValueError):
            bt.parse_product('<input type="hidden" name="product" value="7" />')
        with self.assertRaises(ValueError):
            bt.parse_product("<html>nic tu nie ma</html>")

    def test_odrzuca_adresy_zabronione_w_robots(self):
        for bad in (bt.BASE + "/catalogsearch/result/?q=taart",
                    bt.BASE + "/cakeboards?merk=pme",
                    "https://example.com/produkt"):
            with self.assertRaises(ValueError, msg=bad):
                bt.product(bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
