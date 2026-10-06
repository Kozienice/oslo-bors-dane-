# oslo-bors-dane-

Warstwa danych dla projektu "Oslo Bors" (zadania zaplanowane PORTFEL i PIATEK w Claude).
GitHub Actions pobiera surowe dane w dni robocze i zapisuje je w `data/`. Zadania czytaja je przez
`https://raw.githubusercontent.com/Kozienice/oslo-bors-dane-/main/data/...` i licza w kodzie.

## Co jest pobierane (oslo.py, wersja 0.3)
- API newsweb: lista komunikatow 26 tickerow z 14 dni (`data/komunikaty.csv`, surowe `data/raw/newsweb/lista/`),
  tresc komunikatow z 7 dni (`data/raw/newsweb/tresc/{messageId}.json` i `.txt`),
  zalaczniki PDF dla flaggingu, transakcji insiderow i inside information (EKSPERYMENTALNE, adres nieudokumentowany).
- Norges Bank: kursy referencyjne USD, EUR, SEK -> NOK (`data/waluty.csv`).
- FRED: DCOILBRENTEU, MCOILBRENTEU, PNGASEUUSDM (`data/fred/`).
- Kursy zamkniecia z Yahoo chart API (EKSPERYMENTALNE, klasa 4), 1 rok sesji (od 0.3.1, wczesniej 1 miesiac): `data/kursy.csv`.
- Rekomendacje brokerow (EKSPERYMENTALNE od 0.2.0): listy depesz MarketScreener (news-broker-research, news) dla
  VAR, NAS, AFG, TGS, BNOR oraz strony Nordnet z depeszami Direkt/TDN. Surowe: `data/raw/rekomendacje/{ticker}_{zrodlo}.txt`
  (okna tekstu bez znacznikow wokol trafien; w status.json sha256 pliku i sha256 oryginalnej odpowiedzi). Pochodne:
  `data/rekomendacje.csv` - wiersze z frazami o celach/ratingach, kolumna `data_w_otoczeniu` skopiowana 1:1 z sasiedztwa
  wiersza (moze byc pusta lub nietrafiona). Klasa do ustalenia po 2 tygodniach porownania z rachunkiem DNB.
- Krotkie pozycje (od 0.3.0, klasa 1): rejestr Finanstilsynet https://ssr.finanstilsynet.no/api/v2/instruments
  (pozycje >= 0,5% kapitalu, aktualizacja w dni sesyjne ok. 15:30). Surowe: `data/raw/finanstilsynet/instruments.json.gz`
  (sha256 pliku gz i sha256 oryginalnej odpowiedzi w status.json). Pochodne: `data/shorty.csv` (ostatni stan kazdej spolki),
  `data/shorty_pozycje.csv` (aktywne pozycje z nazwami posiadaczy), `data/shorty_historia.csv` (zdarzenia z 120 dni).

## Kontrola
`data/status.json`: czas uruchomienia (UTC i Oslo), dla kazdego pliku adres, kod HTTP, rozmiar, sha256,
kontrole spojnosci i bledy. `data/podsumowanie.md`: skrot stanu w kilku liniach.
Zadnej liczby nie wpisano recznie.

## Harmonogram (UTC)
04:45, 06:20, 07:20, 14:40 i 15:40 w dni robocze (06:20/07:20 = ok. 08:20 Oslo latem/zima). GitHub opoznia harmonogram nawet o godziny, dlatego zadania PORTFEL i PIATEK same uruchamiaja workflow (gh api .../dispatches). Recznie: Actions -> pobierz-dane-oslo -> Run workflow.
