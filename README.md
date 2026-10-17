# cukrowa dusza

Liczenie kosztu tortów z aktualnych cen Albert Heijn i Baktotaal. Wpisujesz gramaturę,
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
    catalog.json         Twoje składniki → produkty w sklepach (edytujesz ręcznie)
    prices.json          ceny                            (pisze GitHub Actions)
  icons/napis.png        napis z logo, uzywany jako maska CSS
  sw.js                  offline + automatyczne aktualizacje
  tests.html             47 testów silnika, otwierasz w przeglądarce
brand/
  logo-zrodlo.png        logo "cukrowa dusza" - zrodlo ikon i napisu
tools/
  sync_prices.py         pobieranie cen z obu sklepów
  baktotaal.py           odczyt cen z baktotaal.nl
  find_baktotaal.py      wyszukiwarka produktów w baktotaal.nl
  catalog_keys.py        klucze katalogu wg źródła (używa workflow)
  test_sync.py           19 testów części pythonowej
  summary.py             podsumowanie przebiegu
  make_icons.py          generator ikon z logo (macOS, uzywa sips)
  make_wordmark.py       wycina napis z logo jako PNG z przezroczystoscia
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

## Dwa sklepy, dwie różne drogi

| | Albert Heijn | Baktotaal |
|---|---|---|
| co | mąka, masło, jajka, nabiał | podkłady, barwniki, opakowania, dekoracje |
| dostęp | przez aktora Apify | zwykły GET, bez pośrednika |
| pinowanie | kod EAN z opakowania | adres strony produktu |
| wymaga tokenu | tak | nie |

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

### Baktotaal: brutto, nigdy netto

Sklep nie ma ochrony antybotowej, a `robots.txt` pozwala na strony produktów —
wystarczy zwykły GET. Są jednak dwie pułapki, obie obsłużone w `tools/baktotaal.py`:

**Dane strukturalne JSON-LD podają raz brutto, raz netto.** Dla prostego produktu
cena w JSON-LD to brutto (sprinkles 6,99 = 6,99), ale dla wariantu produktu
złożonego netto (cakeboard 1,31 przy wyświetlanych 1,59 — różnica to 21% VAT).
Branie JSON-LD wprost zaniżyłoby koszt podkładu o jedną piątą. Dlatego cena
bierze się z `data-price-amount` głównego produktu — z tej liczby, którą sklep
pokazuje i którą płacisz. Test `test_wariant_NIE_bierze_netto_z_json_ld`
pilnuje, żeby ten błąd nie wrócił.

**Strona zawiera ceny produktów polecanych.** Bez zakotwiczenia w głównym
produkcie (pierwszy `input[name=product]`) łatwo odczytać cenę zupełnie
innego towaru.

Netto i stawka VAT zapisują się tylko wtedy, gdy da się je ustalić pewnie.
Stosunek 1,00 nie znaczy „zero VAT", tylko „JSON-LD już podał brutto" — pole,
które znaczy dwie różne rzeczy, prędzej czy później zostanie źle użyte.

### Dodawanie produktów z Baktotaal

Wyszukiwarki sklepu nie wolno używać (`robots.txt` zabrania `/catalogsearch/`),
więc szukamy w sitemapie, którą sklep publikuje właśnie w tym celu:

```bash
python3 tools/find_baktotaal.py cakeboard rond 25 --ceny
```

Narzędzie wypisze adresy z cenami i gotowy wpis do wklejenia w `catalog.json`.
Sitemapa (16 MB, 14 tys. produktów) cachuje się lokalnie na dobę.

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
- cena **nigdy nie pobrana** → produkt nie ma `syncedAt`, a aplikacja wprost pisze
  „cena przykładowa"; po przebiegu z `--only` reszta nie udaje świeżej
- produkt nieznaleziony → stara cena zostaje, oznaczona `ok: false`
- awaria API albo zero wyników → **plik nie jest nadpisywany**, workflow kończy się błędem
- brak ceny w kalkulacji → składnik liczy się jako `null`, **nigdy jako zero**,
  a aplikacja wyraźnie ostrzega, że nie jest doliczony

## Marka

Ikona i napis pochodza z `brand/logo-zrodlo.png`. Oba generatory sa odtwarzalne:

```bash
python3 tools/make_icons.py      # docs/icons/icon-*.png
python3 tools/make_wordmark.py   # docs/icons/napis.png
```

**Dlaczego napis jest grafika, a nie czcionka.** Logo uzywa Brittany Signature,
ktora jest darmowa wylacznie do uzytku osobistego - autor (Creatype Studio) pisze
wprost "NO COMMERCIAL USE ALLOWED", a licencja komercyjna jest platna. Do tego
repozytorium musi byc publiczne, wiec plik czcionki bylby publicznie do pobrania,
czyli redystrybuowany. Napis w logo to grafika nalezaca do wlasciciela marki,
wiec `make_wordmark.py` wycina go wprost z logo: wynik jest identyczny z logo,
a nie "podobny", i nic nie jest redystrybuowane.

Napis trafia do interfejsu jako **maska CSS**, nie jako obrazek w kolorze -
dzieki temu jeden plik przyjmuje kolor akcentu i dziala w obu motywach.

Nazwa pod ikona na ekranie domowym i tak zawsze renderuje sie fontem systemowym;
iOS nie pozwala jej zmienic.

### Kolory

| | jasny | ciemny |
|---|---|---|
| akcent | `#A8801F` | `#D9B452` |

Zloto z logo (`#C9A227`) ma na bieli kontrast 2,2:1, czyli ponizej normy
czytelnosci - stad przyciemnienie w jasnym motywie i rozjasnienie w ciemnym.
Czerwien ostrzezen i zielen marzy zostaja poza paleta marki: kolor, ktory mowi
"sprawdz cene", musi odcinac sie od brandingu, a nie z nim zlewac.

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
