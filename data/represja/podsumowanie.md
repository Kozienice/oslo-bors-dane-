# Monitor represji finansowej - stan 2026-11-23T15:54:55Z

Zrodla oficjalne (FRED, Norges Bank, EBC, Eurostat, NBP). Szczegoly i adresy: data/represja/status.json.

## Serie

| Seria | Kraj | Ostatnia data | Wartosc | Opis |
|---|---|---|---|---|
| US_FED_GORNA | US | 2026-11-23 | 4.00 | Fed: gorna granica przedzialu stopy funduszy federalnych, % |
| US_IORB | US | 2026-11-23 | 3.90 | Fed: oprocentowanie rezerw bankow (IORB), % |
| US_REZERWY | US | 2026-11-18 | 2979656 | Fed: rezerwy bankow, mld USD (tygodniowo) |
| US_10Y | US | 2026-11-19 | 5.04 | USA: rentownosc obligacji 10Y, % |
| US_10Y_REALNA | US | 2026-11-19 | 2.88 | USA: realna rentownosc 10Y (TIPS), % |
| US_CPI | US | 2026-10-01 | 337.476 | USA: CPI, indeks (r/r liczone w skrypcie) |
| US_BANKI_SKARB | US | 2026-10-01 | 4786.9070 | USA: obligacje skarbowe i agencji w bankach komercyjnych, mld USD |
| US_BANKI_AKTYWA | US | 2026-11-11 | 26143.8881 | USA: aktywa ogolem bankow komercyjnych, mld USD |
| NO_10Y_OECD | NO | 2026-10-01 | 4.43304545450000 | Norwegia: rentownosc dlugoterminowa (OECD, miesiecznie), % |
| PL_10Y_OECD | PL | 2026-10-01 | 6.320000000 | Polska: rentownosc dlugoterminowa (OECD, miesiecznie), % |
| EA_10Y_OECD | EA | 2026-01-01 | 3.2209840909000000 | Strefa euro: rentownosc dlugoterminowa (OECD, miesiecznie), % |
| NO_STOPA | NO | 2026-11-20 | 4.5 | Norges Bank: stopa depozytowa (styringsrenten), % |
| NO_10Y | NO | 2026-11-20 | 4.246 | Norwegia: rentownosc obligacji 10Y (Norges Bank), % |
| EA_DFR | EA | 2026-09-16 | 2.5 | EBC: stopa depozytowa (DFR), % |
| EA_10Y | EA | 2026-11-20 | 3.3607776552 | Strefa euro: krzywa AAA, 10Y, % |
| PL_10Y | PL | 2026-10 | 6.32 | Polska: rentownosc 10Y (kryterium konwergencji), % |
| EA_BANKI_RZAD | EA | BLAD | | Strefa euro: dluzne papiery rzadowe w bilansie bankow (MFI), mln EUR |
| EA_BANKI_AKTYWA | EA | 2026-09 | 44923283.1521 | Strefa euro: aktywa ogolem bankow (MFI), mln EUR |
| NO_HICP | NO | 2026-10 | 3.5 | Norwegia: HICP r/r (Eurostat, ECOICOP ver.2), % |
| PL_HICP | PL | 2026-10 | 3.7 | Polska: HICP r/r (Eurostat, ECOICOP ver.2), % |
| EA_HICP | EA | 2026-10 | 4.0 | Strefa euro: HICP r/r (Eurostat, ECOICOP ver.2, sklad zmienny), % |

## Wskazniki pochodne

| Wskaznik | Miesiac | Wartosc | Rok wczesniej | Wyliczenie |
|---|---|---|---|---|
| NO_REALNA_10Y | 2026-10 | 0.93 | 1.10 | NO_10Y (koniec miesiaca) minus NO_HICP |
| PL_REALNA_10Y | 2026-10 | 2.62 | 2.61 | PL_10Y (koniec miesiaca) minus PL_HICP |
| US_REALNA_10Y | 2026-09 | 1.57 | 1.14 | US_10Y (koniec miesiaca) minus US_CPI_RR |
| EA_REALNA_10Y | 2026-10 | -0.63 | 0.62 | EA_10Y (koniec miesiaca) minus EA_HICP |
| US_UDZIAL_RZAD_W_AKTYWACH_BANKOW | 2026-10 | 18.35 | 19.14 | US_BANKI_SKARB / US_BANKI_AKTYWA x 100 |

## Stopy NBP (data/represja/nbp_stopy.csv)

- ref Stopa referencyjna: 3.75 % (od 2026-03-05)
- lom Stopa lombardowa: 4.25 % (od 2026-03-05)
- dep Stopa depozytowa: 3.25 % (od 2026-03-05)
- red Stopa redyskontowa weksli: 3.80 % (od 2026-03-05)
- dys Stopa dyskontowa weksli: 3.85 % (od 2026-03-05)
- rozwpw - od środków złotowych i środków w walutach obcych zgromadzonych na rachunkach bankowych, od środków uzyskanych z tytułu emisji papierów wartościowych : 3.50 % (od 2022-03-31)
- rorepo - od środków uzyskanych z tytułu operacji repo i sell-buy-back oraz środków pozyskanych co najmniej na 2 lata: 0.00 % (od 2018-03-01)
- rowred Oprocentowanie środków rezerwy obowiązkowej: 3.75 % (od 2026-03-05)
