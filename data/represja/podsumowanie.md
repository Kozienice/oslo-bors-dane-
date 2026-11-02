# Monitor represji finansowej - stan 2026-11-02T13:27:12Z

Zrodla oficjalne (FRED, Norges Bank, EBC, Eurostat, NBP). Szczegoly i adresy: data/represja/status.json.

## Serie

| Seria | Kraj | Ostatnia data | Wartosc | Opis |
|---|---|---|---|---|
| US_FED_GORNA | US | 2026-11-02 | 4.00 | Fed: gorna granica przedzialu stopy funduszy federalnych, % |
| US_IORB | US | 2026-11-02 | 3.90 | Fed: oprocentowanie rezerw bankow (IORB), % |
| US_REZERWY | US | 2026-10-28 | 2893770 | Fed: rezerwy bankow, mld USD (tygodniowo) |
| US_10Y | US | 2026-10-29 | 4.98 | USA: rentownosc obligacji 10Y, % |
| US_10Y_REALNA | US | 2026-10-29 | 2.63 | USA: realna rentownosc 10Y (TIPS), % |
| US_CPI | US | 2026-09-01 | 336.298 | USA: CPI, indeks (r/r liczone w skrypcie) |
| US_BANKI_SKARB | US | 2026-09-01 | 4783.6617 | USA: obligacje skarbowe i agencji w bankach komercyjnych, mld USD |
| US_BANKI_AKTYWA | US | 2026-10-21 | 26080.1895 | USA: aktywa ogolem bankow komercyjnych, mld USD |
| NO_10Y_OECD | NO | 2026-09-01 | 4.40580952380952 | Norwegia: rentownosc dlugoterminowa (OECD, miesiecznie), % |
| PL_10Y_OECD | PL | 2026-09-01 | 6.230000000 | Polska: rentownosc dlugoterminowa (OECD, miesiecznie), % |
| EA_10Y_OECD | EA | 2026-01-01 | 3.2209840909000000 | Strefa euro: rentownosc dlugoterminowa (OECD, miesiecznie), % |
| NO_STOPA | NO | 2026-10-30 | 4.5 | Norges Bank: stopa depozytowa (styringsrenten), % |
| NO_10Y | NO | 2026-10-30 | 4.435 | Norwegia: rentownosc obligacji 10Y (Norges Bank), % |
| EA_DFR | EA | 2026-09-16 | 2.5 | EBC: stopa depozytowa (DFR), % |
| EA_10Y | EA | 2026-10-30 | 3.3650469366 | Strefa euro: krzywa AAA, 10Y, % |
| PL_10Y | PL | 2026-09 | 6.23 | Polska: rentownosc 10Y (kryterium konwergencji), % |
| EA_BANKI_RZAD | EA | 2026-09 | 2416504.24777969 | Strefa euro: dluzne papiery rzadowe w bilansie bankow (MFI), mln EUR |
| EA_BANKI_AKTYWA | EA | 2026-09 | 44923283.1521 | Strefa euro: aktywa ogolem bankow (MFI), mln EUR |
| NO_HICP | NO | 2026-09 | 3.4 | Norwegia: HICP r/r (Eurostat, ECOICOP ver.2), % |
| PL_HICP | PL | 2026-09 | 4.0 | Polska: HICP r/r (Eurostat, ECOICOP ver.2), % |
| EA_HICP | EA | 2026-09 | 3.8 | Strefa euro: HICP r/r (Eurostat, ECOICOP ver.2, sklad zmienny), % |

## Wskazniki pochodne

| Wskaznik | Miesiac | Wartosc | Rok wczesniej | Wyliczenie |
|---|---|---|---|---|
| NO_REALNA_10Y | 2026-09 | 1.20 | 0.44 | NO_10Y (koniec miesiaca) minus NO_HICP |
| PL_REALNA_10Y | 2026-09 | 2.23 | 2.57 | PL_10Y (koniec miesiaca) minus PL_HICP |
| US_REALNA_10Y | 2026-09 | 1.57 | 1.14 | US_10Y (koniec miesiaca) minus US_CPI_RR |
| EA_REALNA_10Y | 2026-09 | -0.22 | 0.58 | EA_10Y (koniec miesiaca) minus EA_HICP |
| US_UDZIAL_RZAD_W_AKTYWACH_BANKOW | 2026-09 | 18.39 | 19.01 | US_BANKI_SKARB / US_BANKI_AKTYWA x 100 |
| EA_UDZIAL_RZAD_W_AKTYWACH_BANKOW | 2026-09 | 5.38 | 5.16 | EA_BANKI_RZAD / EA_BANKI_AKTYWA x 100 |

## Stopy NBP (data/represja/nbp_stopy.csv)

- ref Stopa referencyjna: 3.75 % (od 2026-03-05)
- lom Stopa lombardowa: 4.25 % (od 2026-03-05)
- dep Stopa depozytowa: 3.25 % (od 2026-03-05)
- red Stopa redyskontowa weksli: 3.80 % (od 2026-03-05)
- dys Stopa dyskontowa weksli: 3.85 % (od 2026-03-05)
- rozwpw - od środków złotowych i środków w walutach obcych zgromadzonych na rachunkach bankowych, od środków uzyskanych z tytułu emisji papierów wartościowych : 3.50 % (od 2022-03-31)
- rorepo - od środków uzyskanych z tytułu operacji repo i sell-buy-back oraz środków pozyskanych co najmniej na 2 lata: 0.00 % (od 2018-03-01)
- rowred Oprocentowanie środków rezerwy obowiązkowej: 3.75 % (od 2026-03-05)
