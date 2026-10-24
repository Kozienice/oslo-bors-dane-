# oslo-bors-dane-

Warstwa danych dla projektu "Oslo Bors" (zadania zaplanowane PORTFEL i PIATEK w Claude).
GitHub Actions pobiera surowe dane w dni robocze i zapisuje je w `data/`. Zadania czytaja je przez
`https://raw.githubusercontent.com/Kozienice/oslo-bors-dane-/main/data/...` i licza w kodzie.

## Bufor bezpieczenstwa (od 0.7.0, decyzja wlasciciela 24.10.2026)
Repo jest publiczne, wiec trafiaja tu tylko dane pochodne potrzebne zadaniom: komunikaty gieldowe, kursy, serie makro,
naglowki prasy (tytul, data, adres, trafienia). Zrodla, ktorych regulamin zakazuje automatycznego pobierania
albo redystrybucji (Nordnet, MarketScreener, Yahoo), sa wylaczone. Nie trafiaja: surowe kopie stron
i kanalow, leady artykulow, nazwy uzytkownikow, id profili, awatary, opisy profili, kraj ani zadne inne dane o autorach
wpisow. Kontrola na koncu przebiegu (`kontrola_autorow` w oslo.py) usuwa plik ze sladem danych profilu, a krok workflow
przed commitem zatrzymuje zapis, gdyby cos przeszlo. Research wylacznie na wlasny uzytek wlasciciela.

## Co jest pobierane (oslo.py, wersja 0.7)
- API newsweb: lista komunikatow 26 tickerow z 14 dni (`data/komunikaty.csv`, surowe `data/raw/newsweb/lista/`),
  tresc komunikatow z 7 dni (`data/raw/newsweb/tresc/{messageId}.json` i `.txt`),
  zalaczniki PDF dla flaggingu, transakcji insiderow i inside information (EKSPERYMENTALNE, adres nieudokumentowany).
- Norges Bank: kursy referencyjne USD, EUR, SEK -> NOK (`data/waluty.csv`).
- FRED: DCOILBRENTEU, MCOILBRENTEU, PNGASEUUSDM (`data/fred/`).
- Kursy zamkniecia z Yahoo chart API: WYLACZONE od 24.10.2026 - warunki Yahoo
  (https://legal.yahoo.com/xw/en/yahoo/terms/otos/index.html, sekcja 2(d) pkt 9 i 2(h)) zabraniaja automatycznego zbierania
  danych i ich dystrybucji; `data/kursy.csv` i `data/raw/kursy/` usuniete. Flaga `KURSY_WLACZONE` w oslo.py.
- WYLACZONE od 24.10.2026 (dwa punkty ponizej): regulaminy Nordnet
  (https://www.nordnet.se/faq/ovrigt/regler-foer-scraping-och-automatisk-datainsamling) i MarketScreener
  (https://www.marketscreener.com/navigation/contrat-4T.htm, art. 4) zabraniaja automatycznego pobierania i redystrybucji,
  mimo ze robots.txt tych sciezek nie blokuje. Flaga `REKOMENDACJE_WLACZONE` w oslo.py; wlaczenie tylko decyzja wlasciciela.
- Rekomendacje brokerow (EKSPERYMENTALNE od 0.2.0): listy depesz MarketScreener (news-broker-research, news) dla
  VAR, NAS, AFG, TGS, BNOR oraz strony Nordnet z depeszami Direkt/TDN. Od 0.7.0 bez surowych okien tekstu
  (`data/raw/rekomendacje/` usuniety); w status.json (`zrodla.rekomendacje.odpowiedzi`) adres, kod, rozmiar i sha256
  odpowiedzi. Pochodne: `data/rekomendacje.csv` - wiersze z frazami o celach/ratingach, kolumna `data_w_otoczeniu`
  skopiowana 1:1 z sasiedztwa wiersza (moze byc pusta lub nietrafiona). Klasa do ustalenia po 2 tygodniach porownania z rachunkiem DNB.
- Forum Nordnet: rezygnacja wlasciciela 24.10.2026 (regulamin Nordnet zakazuje automatycznego zbierania danych).
- Krotkie pozycje (od 0.3.0, klasa 1): rejestr Finanstilsynet https://ssr.finanstilsynet.no/api/v2/instruments
  (pozycje >= 0,5% kapitalu, aktualizacja w dni sesyjne ok. 15:30). Surowe: `data/raw/finanstilsynet/instruments.json.gz`
  (sha256 pliku gz i sha256 oryginalnej odpowiedzi w status.json). Pochodne: `data/shorty.csv` (ostatni stan kazdej spolki),
  `data/shorty_pozycje.csv` (aktywne pozycje z nazwami posiadaczy), `data/shorty_historia.csv` (zdarzenia z 120 dni).
- Prasa NO (od 0.5.0, zrodla od 0.5.3): naglowki z kanalow publicznych - RSS/Atom: bygg.no, anlegg.bygg.no,
  estatenyheter.no, tu.no, shifter.no, kyst.no, ilaks.no, offshore-energy.biz, anleggsmaskinen.no, vegvesen.no,
  boligprodusentene.no, investornytt.no, energiogklima.no, byggmesteren.as, fishfarmingexpert.com, gcaptain.com,
  hellenicshippingnews.com, northernminer.com, mapa artykulow Finansavisen biezacego
  miesiaca i mapa news offshore-mag.com. Jedno zapytanie na portal na przebieg
  (pauza 3 s, jedna ponowna proba), tresci artykulow nie pobieramy. Od 0.7.0 w repo tylko tytul, data, adres i trafienia:
  bez leadu i bez surowych kopii kanalow (`data/raw/prasa/` usuniety; slad pobrania w `zrodla.prasa.odpowiedzi`).
  `data/prasa.csv` akumuluje 60 dni; `trafienia` = slowa kluczowe spolek i tematow liczone na tytule, opisie z kanalu
  (tylko w trakcie przebiegu) i adresie, w tym klucze fuzji MA, CONOCO, ENI, AKER_TRG. Celowo POMINIETE (robots.txt lub warunki kanalu zabraniaja automatycznego przetwarzania albo
  blokuja boty AI; wynik sondy w `sonda/wynik3.json`): dn.no, e24.no, energiwatch.no, europower.no, intrafish.no,
  investtech.com, nettavisen.no, nrk.no, tradewindsnews.com, upstreamonline.com, aftenposten.no, vg.no, tv2.no,
  aksjelive.no, borsen.dk, di.se, kauppalehti.fi, placera.se, oilprice.com. Nowe portale: `narzedzia/sonda.py`
  (workflow sonda-portali) sprawdza robots.txt i kanaly przed dodaniem.

## Kontrola
`data/status.json`: czas uruchomienia (UTC i Oslo), dla kazdego pliku adres, kod HTTP, rozmiar, sha256,
kontrole spojnosci i bledy. `data/podsumowanie.md`: skrot stanu w kilku liniach.
Zadnej liczby nie wpisano recznie.

## Harmonogram (UTC)
04:45, 06:20, 07:20, 14:40 i 15:40 w dni robocze (06:20/07:20 = ok. 08:20 Oslo latem/zima). GitHub opoznia harmonogram nawet o godziny, dlatego zadania PORTFEL i PIATEK same uruchamiaja workflow (gh api .../dispatches). Recznie: Actions -> pobierz-dane-oslo -> Run workflow.

## Monitor represji finansowej (represja.py, osobny workflow monitor-represji)
Tlo: IMF Working Paper 26/160 "The Coming Great Repression?" (2026). Liczby dla czterech bankow centralnych: Norges Bank, NBP, Fed, EBC.
Zrodla oficjalne: FRED, Norges Bank, EBC, Eurostat, NBP. Wynik w `data/represja/`: `serie/*.csv` (surowe serie),
`wskazniki.csv` (realna rentownosc 10Y = rentownosc minus inflacja r/r; udzial obligacji rzadowych w aktywach bankow USA
i strefy euro, liczone w skrypcie), `nbp_stopy.csv`, `podsumowanie.md`, `status.json` (adresy, kody HTTP, sha256, bledy).
Osobny katalog i osobny status: nie zmienia plikow z `oslo.py`. Harmonogram: poniedzialek 05:10 UTC + reczne uruchomienie.
Czyta go miesieczne zadanie zaplanowane w Claude (projekt Oslo Bors).
