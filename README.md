# oslo-bors-dane-

Warstwa danych dla projektu "Oslo Bors" (zadania zaplanowane PORTFEL i PIATEK w Claude).
GitHub Actions pobiera surowe dane w dni robocze i zapisuje je w `data/`. Zadania czytaja je przez
`https://raw.githubusercontent.com/Kozienice/oslo-bors-dane-/main/data/...` i licza w kodzie.

## Co jest pobierane (oslo.py, wersja 0.2)
- API newsweb: lista komunikatow 26 tickerow z 14 dni (`data/komunikaty.csv`, surowe `data/raw/newsweb/lista/`),
  tresc komunikatow z 7 dni (`data/raw/newsweb/tresc/{messageId}.json` i `.txt`),
  zalaczniki PDF dla flaggingu, transakcji insiderow i inside information (EKSPERYMENTALNE, adres nieudokumentowany).
- Norges Bank: kursy referencyjne USD, EUR, SEK -> NOK (`data/waluty.csv`).
- FRED: DCOILBRENTEU, MCOILBRENTEU, PNGASEUUSDM (`data/fred/`).
- Kursy zamkniecia z Yahoo chart API (EKSPERYMENTALNE, klasa 4): `data/kursy.csv`.
- Rekomendacje brokerow (EKSPERYMENTALNE od 0.2.0): listy depesz MarketScreener (news-broker-research, news) dla
  VAR, NAS, AFG, TGS, BNOR oraz strony Nordnet z depeszami Direkt/TDN. Surowe: `data/raw/rekomendacje/{ticker}_{zrodlo}.txt`
  (tekst strony bez znacznikow; w status.json sha256 pliku i sha256 oryginalnej odpowiedzi). Pochodne:
  `data/rekomendacje.csv` - wiersze z frazami o celach/ratingach, kolumna `data_w_otoczeniu` skopiowana 1:1 z sasiedztwa
  wiersza (moze byc pusta lub nietrafiona). Klasa do ustalenia po 2 tygodniach porownania z rachunkiem DNB.

## Kontrola
`data/status.json`: czas uruchomienia (UTC i Oslo), dla kazdego pliku adres, kod HTTP, rozmiar, sha256,
kontrole spojnosci i bledy. `data/podsumowanie.md`: skrot stanu w kilku liniach.
Zadnej liczby nie wpisano recznie.

## Harmonogram (UTC)
04:45, 14:40 i 15:40 w dni robocze. Recznie: Actions -> pobierz-dane-oslo -> Run workflow.
