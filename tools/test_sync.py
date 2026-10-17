#!/usr/bin/env python3
"""Testy czesci pythonowej. Biblioteka standardowa, zero zaleznosci.

    python3 tools/test_sync.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import sync_prices as sp  # noqa: E402


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

    def test_kazdy_wpis_da_sie_zsynchronizowac_albo_jest_reczny(self):
        for key, v in self.items.items():
            if v.get("manual"):
                self.assertIsInstance(v.get("price"), int, key)
            else:
                self.assertTrue(v.get("ean") or v.get("query"),
                                "%s nie ma ani 'ean', ani 'query'" % key)

    def test_ceny_sa_calkowite_w_groszach(self):
        for key, v in self.prices["products"].items():
            self.assertIsInstance(v["price"], int, key)
            if v.get("bonusPrice") is not None:
                self.assertIsInstance(v["bonusPrice"], int, key)
                self.assertLess(v["bonusPrice"], v["price"], key)


if __name__ == "__main__":
    unittest.main(verbosity=2)
