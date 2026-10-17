# Tortownik

Liczenie kosztu tortów z aktualnych cen Albert Heijn. Wpisujesz gramaturę,
aplikacja dolicza robociznę, prąd i marżę, i podaje cenę sprzedaży oraz koszt porcji.

Aplikacja webowa (PWA) dodawana do ekranu domowego iPhone'a. Bez Xcode,
bez konta Apple Developer, bez App Store. Push do GitHuba = nowa wersja na telefonie.

## Zero zależności

Nie ma `package.json`, bundlera ani `node_modules`. Aplikacja to moduły ES ładowane
wprost przez przeglądarkę, a narzędzia to biblioteka standardowa Pythona.
Nie ma czego instalować ani aktualizować.

```
docs/                    ← GitHub Pages serwuje stąd
  index.html  app.css    powłoka i style
  js/
    money.js             kwoty wyłącznie w groszach (int)
    calc.js              silnik kalkulacji — czyste funkcje, zero DOM
    store.js             IndexedDB: receptury, stawka, marże
    prices.js            ładowanie katalogu i cen
    ui.js  app.js        renderowanie i logika
  data/
    catalog.json         Twoje składniki → produkty AH   (edytujesz ręcznie)
    prices.json          ceny                            (pisze GitHub Actions)
  sw.js                  offline + automatyczne aktualizacje
  tests.html             47 testów silnika, otwierasz w przeglądarce
tools/
  sync_prices.py         pobieranie cen przez Apify
  test_sync.py           19 testów części pythonowej
  summary.py             podsumowanie przebiegu
  make_icons.py          generator ikon
  serve.py               lokalny podgląd
```

## Uruchomienie lokalnie

```bash
python3 tools/serve.py
```

→ `http://localhost:8765` (aplikacja) i `http://localhost:8765/tests.html` (testy).

## Testy

```bash
python3 tools/test_sync.py
```

Silnik kalkulacji: otwórz `localhost:8765/tests.html` — musi pokazać **47 / 47 przeszło**.

## Synchronizacja cen

```bash
export APIFY_TOKEN=apify_api_...
python3 tools/sync_prices.py --dry-run     # pokaż różnice, nie zapisuj
python3 tools/sync_prices.py               # zapisz
python3 tools/sync_prices.py --only maslo  # pojedynczy składnik
```

W GitHubie robi to codziennie workflow `Ceny Albert Heijn` (05:15 UTC), a commituje
tylko wtedy, gdy ceny faktycznie się zmieniły. Można go też odpalić ręcznie
(`Actions` → `Run workflow`).

### Dlaczego przez Apify, a nie wprost z AH

Albert Heijn nie ma publicznego API i stoi za Akamai Bot Manager. Sprawdzone na żywo:

| próba | wynik |
|---|---|
| `POST api.ah.nl/mobile-auth/v1/auth/token/anonymous` przez curl | **503** (odrzut po fingerprincie TLS) |
| `fetch()` z przeglądarki na `api.ah.nl` | `Failed to fetch` — **brak CORS** dla obcych originów |
| strona produktu `ah.nl` | 200, ale 2,6 kB strony-wyzwania, bez danych i bez JSON-LD |
| introspekcja GraphQL | wyłączona przez AH (marzec 2026) |

Własny scraper z GitHub Actions psułby się co kilka tygodni. Aktor Apify utrzymuje
obejście po swojej stronie. Zamiana źródła to jedna stała `ACTOR` w `sync_prices.py`.

### Pinowanie składników

Aktor nie potrafi szukać po `webshopId`, ale potrafi po **kodzie EAN** — dlatego
w `catalog.json` składnik pinuje się do kodu kreskowego z opakowania:

```json
"maslo": { "name": "Masło", "ean": "8710400514206", "pack": 250, "unit": "g" }
```

Bez `ean` działa `query` (nazwa), ale wynik jest oznaczany jako **niepotwierdzony**,
dopóki nie dopiszesz `ean` albo `sku`.

**Katalog jest źródłem prawdy dla gramatury i jednostki — synchronizacja zmienia
wyłącznie cenę.** Gdy AH zmieni opakowanie z 250 g na 200 g, dostaniesz ostrzeżenie
zamiast cichego zaniżenia kosztu o 20%.

### Czego skrypt nigdy nie zrobi

Od ceny składnika zależy cena, po której sprzedajesz tort, więc:

- skok ceny **>40%** → odrzucony jako podmiana produktu, stara cena zachowana
- produkt nieznaleziony → stara cena zostaje, oznaczona `ok: false`
- awaria API albo zero wyników → **plik nie jest nadpisywany**, workflow kończy się błędem
- brak ceny w kalkulacji → składnik liczy się jako `null`, **nigdy jako zero**,
  a aplikacja wyraźnie ostrzega, że nie jest doliczony

## Prywatność

GitHub Pages na darmowym koncie wymaga publicznego repo, więc:

- **w repo:** kod i ceny AH (informacja publiczna)
- **tylko na telefonie:** receptury, stawka godzinowa, marże — IndexedDB, nigdy nie wychodzą

Kopia zapasowa: Ustawienia → *Zapisz kopię do Plików*. To jedyna droga, bo nic
nie trafia do chmury.

## Instalacja na iPhonie

1. Otwórz adres GitHub Pages w **Safari** (nie w Chrome — tylko Safari potrafi instalować PWA na iOS)
2. Udostępnij → **Dodaj do ekranu domowego**
3. Uruchom z ikony — pełny ekran, bez paska przeglądarki, działa offline
