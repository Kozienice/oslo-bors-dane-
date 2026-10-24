"""Monitor represji finansowej (miesieczny) - liczby dla Norges Bank, NBP, Fed i EBC.

Tlo: IMF WP/26/160 "The Coming Great Repression?" (Bolhuis i in., 2026). Sygnaly, ktore praca laczy z represja:
oprocentowanie rezerw bankow ponizej rynku, realne oprocentowanie dlugu ponizej zera przy wysokim dlugu,
rosnacy udzial obligacji skarbowych w aktywach bankow.

Zrodla (tylko oficjalne API, klasa 1):
- FRED (St. Louis Fed): stopy Fed, oprocentowanie rezerw (IORB), rentownosci USA, realna rentownosc TIPS,
  obligacje skarbowe w bankach komercyjnych USA, rentownosci 10Y OECD dla NO/PL/strefy euro.
- Norges Bank (data.norges-bank.no): stopa depozytowa, rentownosc obligacji 10Y.
- EBC (data-api.ecb.europa.eu): stopa depozytowa, rentownosc 10Y strefy euro, HICP strefy euro i Polski,
  rentownosc 10Y Polski (kryterium konwergencji), bilans bankow strefy euro.
- Eurostat: HICP r/r dla Norwegii, Polski i strefy euro.
- NBP (static.nbp.pl): stopy procentowe NBP (plik XML).

Wynik: data/represja/ - osobny katalog i osobny status.json, zeby nie ruszac danych z oslo.py.
Seria, ktorej nie da sie pobrac, dostaje ok=false w status.json - skrypt nie przerywa pracy.
"""
import csv
import hashlib
import io
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

WERSJA = "0.2"
OUT = Path("data") / "represja"
RAW = OUT / "raw"
UA = f"oslo-bors-dane/represja-{WERSJA} (+https://github.com/Kozienice/oslo-bors-dane-)"
TIMEOUT = 60
OKNO = 400  # ile ostatnich obserwacji trzymac w pliku serii (dzienne ~ 1,5 roku, miesieczne > 30 lat)

teraz = datetime.now(timezone.utc)
status = {"uruchomienie_utc": teraz.strftime("%Y-%m-%dT%H:%M:%SZ"), "wersja_skryptu": WERSJA,
          "serie": {}, "pliki": {}, "bledy": []}

# id_serii -> (zrodlo, klucz, kraj, opis)
SERIE = {
    # USA / Fed
    "US_FED_GORNA": ("fred", "DFEDTARU", "US", "Fed: gorna granica przedzialu stopy funduszy federalnych, %"),
    "US_IORB": ("fred", "IORB", "US", "Fed: oprocentowanie rezerw bankow (IORB), %"),
    "US_REZERWY": ("fred", "WRESBAL", "US", "Fed: rezerwy bankow, mld USD (tygodniowo)"),
    "US_10Y": ("fred", "DGS10", "US", "USA: rentownosc obligacji 10Y, %"),
    "US_10Y_REALNA": ("fred", "DFII10", "US", "USA: realna rentownosc 10Y (TIPS), %"),
    "US_CPI": ("fred", "CPIAUCSL", "US", "USA: CPI, indeks (r/r liczone w skrypcie)"),
    "US_BANKI_SKARB": ("fred", "USGSEC", "US", "USA: obligacje skarbowe i agencji w bankach komercyjnych, mld USD"),
    "US_BANKI_AKTYWA": ("fred", "TLAACBW027SBOG", "US", "USA: aktywa ogolem bankow komercyjnych, mld USD"),
    # OECD przez FRED - jednolite miesieczne rentownosci dlugoterminowe
    "NO_10Y_OECD": ("fred", "IRLTLT01NOM156N", "NO", "Norwegia: rentownosc dlugoterminowa (OECD, miesiecznie), %"),
    "PL_10Y_OECD": ("fred", "IRLTLT01PLM156N", "PL", "Polska: rentownosc dlugoterminowa (OECD, miesiecznie), %"),
    "EA_10Y_OECD": ("fred", "IRLTLT01EZM156N", "EA", "Strefa euro: rentownosc dlugoterminowa (OECD, miesiecznie), %"),
    # Norges Bank
    "NO_STOPA": ("norges", "IR/B.KPRA.SD.R", "NO", "Norges Bank: stopa depozytowa (styringsrenten), %"),
    "NO_10Y": ("norges", "GOVT_GENERIC_RATES/B.10Y.GBON", "NO", "Norwegia: rentownosc obligacji 10Y (Norges Bank), %"),
    # EBC
    "EA_DFR": ("ecb", "FM/B.U2.EUR.4F.KR.DFR.LEV", "EA", "EBC: stopa depozytowa (DFR), %"),
    "EA_10Y": ("ecb", "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y", "EA", "Strefa euro: krzywa AAA, 10Y, %"),
    "PL_10Y": ("ecb", "IRS/M.PL.L.L40.CI.0000.PLN.N.Z", "PL", "Polska: rentownosc 10Y (kryterium konwergencji), %"),
    "EA_BANKI_RZAD": ("ecb", "BSI/M.U2.N.A.A30.A.1.U2.2100.Z01.E", "EA",
                      "Strefa euro: dluzne papiery rzadowe w bilansie bankow (MFI), mln EUR"),
    "EA_BANKI_AKTYWA": ("ecb", "BSI/M.U2.N.A.T00.A.1.Z5.0000.Z01.E", "EA", "Strefa euro: aktywa ogolem bankow (MFI), mln EUR"),
    # Eurostat
    "NO_HICP": ("eurostat", "NO", "NO", "Norwegia: HICP r/r (Eurostat, ECOICOP ver.2), %"),
    "PL_HICP": ("eurostat", "PL", "PL", "Polska: HICP r/r (Eurostat, ECOICOP ver.2), %"),
    "EA_HICP": ("eurostat", "EA", "EA", "Strefa euro: HICP r/r (Eurostat, ECOICOP ver.2, sklad zmienny), %"),
}


def sesja():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    return s


def get(s, url, params=None):
    try:
        r = s.get(url, params=params, timeout=TIMEOUT)
        time.sleep(0.4)
        return r
    except Exception as e:
        status["bledy"].append(f"GET {url}: {type(e).__name__}: {e}"[:400])
        return None


def zapisz_raw(nazwa, r):
    p = RAW / nazwa
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(r.content)
    status["pliki"][str(p)] = {"url": r.url, "http": r.status_code, "bajty": len(r.content),
                              "sha256": hashlib.sha256(r.content).hexdigest()}


def csv_sdmx(tekst):
    """CSV z API SDMX (Norges Bank, EBC): kolumny TIME_PERIOD i OBS_VALUE, separator ; albo ,"""
    tekst = tekst.lstrip("﻿")
    sep = ";" if tekst.count(";") > tekst.count(",") else ","
    obs = []
    for w in csv.DictReader(io.StringIO(tekst), delimiter=sep):
        d = w.get("TIME_PERIOD") or w.get("Time Period") or ""
        v = (w.get("OBS_VALUE") or w.get("Observation Value") or "").replace(",", ".") if sep == ";" else \
            (w.get("OBS_VALUE") or w.get("Observation Value") or "")
        if d and v not in ("", "NaN"):
            obs.append((d, v))
    return sorted(obs)


def pobierz_fred(s, sid, klucz):
    r = get(s, "https://fred.stlouisfed.org/graph/fredgraph.csv", {"id": klucz})
    if r is None or r.status_code != 200 or b"," not in r.content[:200]:
        return None, r
    rd = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    return [(d, v) for d, v in rd[1:] if v not in ("", ".")], r


def pobierz_norges(s, sid, klucz):
    r = get(s, f"https://data.norges-bank.no/api/data/{klucz}",
            {"format": "csv", "lastNObservations": OKNO, "locale": "en"})
    if r is None or r.status_code != 200:
        return None, r
    return csv_sdmx(r.content.decode("utf-8", "replace")), r


def pobierz_ecb(s, sid, klucz):
    r = get(s, f"https://data-api.ecb.europa.eu/service/data/{klucz}",
            {"format": "csvdata", "lastNObservations": OKNO})
    if r is None or r.status_code != 200:
        return None, r
    return csv_sdmx(r.content.decode("utf-8", "replace")), r


_estat = {}
ESTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_minr"
# Od 2026 HICP w klasyfikacji ECOICOP ver.2 (zbior prc_hicp_minr); stary prc_hicp_manr konczy sie na 2025-12.
# Kody jednostki i pozycji "All-items" odczytywane z etykiet API, nie wpisane na sztywno.


def _js_dekoduj(js, wybor):
    """JSON-stat: wartosci dla wybranych kategorii (dict wymiar->kod), szereg po czasie."""
    wym, rozm = js["id"], js["size"]
    idx = {k: js["dimension"][k]["category"]["index"] for k in wym}
    czasy = sorted(idx["time"], key=idx["time"].get)
    obs = []
    for t in czasy:
        poz = 0
        for k, n in zip(wym, rozm):
            kod = t if k == "time" else wybor.get(k)
            i = idx[k][kod] if kod is not None else 0
            poz = poz * n + i
        v = js["value"].get(str(poz))
        if v is not None:
            obs.append((t, str(v)))
    return obs


def pobierz_eurostat(s, sid, geo):
    if "js" not in _estat:
        _estat["js"] = None
        r0 = get(s, ESTAT, {"geo": "PL", "lastTimePeriod": 1, "lang": "EN"})
        if r0 is None or r0.status_code != 200:
            _estat["r"] = r0
            return None, r0
        d = r0.json()["dimension"]
        lab = lambda w: d[w]["category"].get("label", {})
        wym_poz = next((w for w in d if w not in ("freq", "unit", "geo", "time")), None)
        poz = next((k for k, v in lab(wym_poz).items() if k == "TOTAL" or "all-items" in v.lower() or "all items" in v.lower()), None) \
            if wym_poz else None
        jedn = next((k for k, v in lab("unit").items() if "annual rate" in v.lower()), None) if "unit" in d else None
        if not (wym_poz and poz and jedn):
            status["eurostat_odkrywanie"] = {"wymiary": list(d), **{w: dict(list(lab(w).items())[:12]) for w in d}}
            _estat["r"] = r0
            return None, r0
        _estat["kody"] = {"wymiar_pozycji": wym_poz, "pozycja": poz, "jednostka": jedn}
        r = get(s, ESTAT, [("geo", g) for g in ("NO", "PL", "EA", "EA21", "EA20")] +
                [(wym_poz, poz), ("unit", jedn), ("lang", "EN"), ("sinceTimePeriod", "2015-01")])
        _estat["r"] = r
        if r is not None and r.status_code == 200:
            _estat["js"] = r.json()
            zapisz_raw("eurostat/prc_hicp_minr.json", r)
        status["eurostat_kody"] = _estat["kody"]
    r, js = _estat.get("r"), _estat.get("js")
    if js is None:
        return None, r
    k = _estat["kody"]
    dostepne = js["dimension"]["geo"]["category"]["index"]
    for g in ((geo, "EA21", "EA20") if geo == "EA" else (geo,)):
        if g in dostepne:
            obs = _js_dekoduj(js, {k["wymiar_pozycji"]: k["pozycja"], "unit": k["jednostka"], "geo": g})
            if obs:
                status.setdefault("eurostat_geo", {})[geo] = g
                return obs, r
    return None, r


def nbp(s):
    """Stopy NBP z pliku XML - struktura nieopisana w API, wiec zapis surowy + proba odczytu atrybutow."""
    r = get(s, "https://static.nbp.pl/dane/stopy/stopy_procentowe.xml")
    if r is None or r.status_code != 200:
        status["serie"]["PL_STOPY_NBP"] = {"ok": False, "http": getattr(r, "status_code", None)}
        return
    zapisz_raw("nbp_stopy_procentowe.xml", r)
    wiersze = []
    try:
        root = ET.fromstring(r.content)
        for el in root.iter():
            a = {k.lower(): v for k, v in el.attrib.items()}
            if a.get("id") and a.get("oprocentowanie"):
                wiersze.append([a.get("id"), a.get("nazwa", ""), a.get("oprocentowanie").replace(",", "."),
                                a.get("obowiazuje_od", "") or root.attrib.get("obowiazuje_od", "")])
    except Exception as e:
        status["bledy"].append(f"NBP XML: {type(e).__name__}: {e}"[:400])
    zapisz_csv(OUT / "nbp_stopy.csv", ["id", "nazwa", "oprocentowanie", "obowiazuje_od"], wiersze)
    status["serie"]["PL_STOPY_NBP"] = {"ok": bool(wiersze), "zrodlo": r.url, "wierszy": len(wiersze),
                                      "opis": "NBP: stopy procentowe (referencyjna, depozytowa, lombardowa i inne)"}


def zapisz_csv(p, naglowek, wiersze):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(naglowek)
        w.writerows(wiersze)


def rr(obs):
    """Zmiana r/r w % dla serii miesiecznej indeksu (CPI USA)."""
    slo = {d[:7]: float(v) for d, v in obs}
    out = []
    for d, v in obs:
        rok, mies = int(d[:4]), d[5:7]
        poprz = slo.get(f"{rok - 1}-{mies}")
        if poprz:
            out.append((d[:7], f"{(float(v) / poprz - 1) * 100:.2f}"))
    return out


def ostatnia(obs):
    return obs[-1] if obs else ("", "")


def miesiecznie(obs):
    """Ostatnia obserwacja w kazdym miesiacu -> {RRRR-MM: wartosc}."""
    m = {}
    for d, v in obs:
        m[d[:7]] = float(v)
    return m


def main():
    s = sesja()
    funkcje = {"fred": pobierz_fred, "norges": pobierz_norges, "ecb": pobierz_ecb, "eurostat": pobierz_eurostat}
    dane = {}
    for sid, (zr, klucz, kraj, opis) in SERIE.items():
        try:
            obs, r = funkcje[zr](s, sid, klucz)
        except Exception as e:
            obs, r = None, None
            status["bledy"].append(f"{sid}: {type(e).__name__}: {e}"[:400])
        wpis = {"ok": bool(obs), "zrodlo": zr, "klucz": klucz, "kraj": kraj, "opis": opis,
                "http": getattr(r, "status_code", None), "url": getattr(r, "url", None)}
        if obs:
            obs = obs[-OKNO:]
            dane[sid] = obs
            wpis.update({"ostatnia_data": obs[-1][0], "ostatnia_wartosc": obs[-1][1], "obserwacji": len(obs)})
            zapisz_csv(OUT / "serie" / f"{sid}.csv", ["data", "wartosc"], obs)
            if zr != "eurostat":
                zapisz_raw(f"{zr}/{sid}.csv", r)
        status["serie"][sid] = wpis
    nbp(s)

    # wskazniki pochodne (liczone w kodzie z serii powyzej)
    poch = []
    if "US_CPI" in dane:
        cpi = rr(dane["US_CPI"])
        if cpi:
            zapisz_csv(OUT / "serie" / "US_CPI_RR.csv", ["data", "wartosc"], cpi)
            dane["US_CPI_RR"] = cpi
    infl = {"US": "US_CPI_RR", "NO": "NO_HICP", "PL": "PL_HICP", "EA": "EA_HICP"}
    rent = {"US": "US_10Y", "NO": "NO_10Y", "PL": "PL_10Y", "EA": "EA_10Y"}
    zapas_rent = {"NO": "NO_10Y_OECD", "PL": "PL_10Y_OECD", "EA": "EA_10Y_OECD"}
    zapas_infl = {}
    for kraj in ("NO", "PL", "US", "EA"):
        ks = rent[kraj] if rent[kraj] in dane else zapas_rent.get(kraj)
        ki = infl[kraj] if infl[kraj] in dane else zapas_infl.get(kraj)
        if ks in dane and ki in dane:
            mr, mi = miesiecznie(dane[ks]), miesiecznie(dane[ki])
            wspolne = sorted(set(mr) & set(mi))
            if wspolne:
                m = wspolne[-1]
                rok_temu = f"{int(m[:4]) - 1}{m[4:]}"
                realna = mr[m] - mi[m]
                realna_12 = (mr[rok_temu] - mi[rok_temu]) if rok_temu in mr and rok_temu in mi else None
                poch.append([f"{kraj}_REALNA_10Y", m, f"{realna:.2f}",
                             "" if realna_12 is None else f"{realna_12:.2f}",
                             f"{ks} (koniec miesiaca) minus {ki}"])
    for kraj, a, b in (("US", "US_BANKI_SKARB", "US_BANKI_AKTYWA"), ("EA", "EA_BANKI_RZAD", "EA_BANKI_AKTYWA")):
        if a in dane and b in dane:
            ma, mb = miesiecznie(dane[a]), miesiecznie(dane[b])
            wspolne = sorted(set(ma) & set(mb))
            if wspolne:
                m = wspolne[-1]
                rok_temu = f"{int(m[:4]) - 1}{m[4:]}"
                u = ma[m] / mb[m] * 100
                u12 = ma[rok_temu] / mb[rok_temu] * 100 if rok_temu in ma and rok_temu in mb else None
                poch.append([f"{kraj}_UDZIAL_RZAD_W_AKTYWACH_BANKOW", m, f"{u:.2f}",
                             "" if u12 is None else f"{u12:.2f}", f"{a} / {b} x 100"])
    zapisz_csv(OUT / "wskazniki.csv", ["wskaznik", "miesiac", "wartosc", "wartosc_rok_wczesniej", "wyliczenie"], poch)
    status["wskazniki"] = len(poch)

    # podsumowanie dla zadania miesiecznego
    linie = [f"# Monitor represji finansowej - stan {status['uruchomienie_utc']}", "",
             "Zrodla oficjalne (FRED, Norges Bank, EBC, Eurostat, NBP). Szczegoly i adresy: data/represja/status.json.", "",
             "## Serie", "", "| Seria | Kraj | Ostatnia data | Wartosc | Opis |", "|---|---|---|---|---|"]
    for sid, w in status["serie"].items():
        if w.get("ok") and "ostatnia_data" in w:
            linie.append(f"| {sid} | {w['kraj']} | {w['ostatnia_data']} | {w['ostatnia_wartosc']} | {w['opis']} |")
        elif not w.get("ok"):
            linie.append(f"| {sid} | {w.get('kraj', '')} | BLAD | | {w.get('opis', '')} |")
    linie += ["", "## Wskazniki pochodne", "", "| Wskaznik | Miesiac | Wartosc | Rok wczesniej | Wyliczenie |",
              "|---|---|---|---|---|"] + [f"| {' | '.join(p)} |" for p in poch]
    if status["serie"].get("PL_STOPY_NBP", {}).get("ok"):
        linie += ["", "## Stopy NBP (data/represja/nbp_stopy.csv)", ""]
        with (OUT / "nbp_stopy.csv").open(encoding="utf-8") as f:
            for w in list(csv.reader(f))[1:]:
                linie.append(f"- {w[0]} {w[1]}: {w[2]} % (od {w[3]})")
    (OUT / "podsumowanie.md").write_text("\n".join(linie) + "\n", encoding="utf-8")
    (OUT / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
