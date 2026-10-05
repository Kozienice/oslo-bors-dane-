"""
oslo.py - warstwa pobierania danych dla projektu "Oslo Bors" (zadania PORTFEL i PIATEK).

WERSJA 0.1 (2026-10-02)
- API newsweb (Oslo Bors): lista komunikatow per ticker (14 dni) + pelna tresc kazdego komunikatu z 7 dni
  + zalaczniki PDF komunikatow istotnych (flagging, insider, inside information) z wyciagiem tekstu.
- Norges Bank: kursy referencyjne USD, EUR, SEK -> NOK (CSV z API, 30 ostatnich obserwacji).
- FRED: DCOILBRENTEU (Dated Brent dzienny), MCOILBRENTEU (Brent sredni miesieczny), PNGASEUUSDM (gaz UE miesieczny).
- Kursy zamkniecia: Yahoo chart API (EKSPERYMENTALNE, klasa 4) - do potwierdzenia drugim zrodlem w zadaniu.

WERSJA 0.2.0 (2026-10-05)
- Rekomendacje brokerow (EKSPERYMENTALNE): listy depesz MarketScreener (news-broker-research i news) dla portfela
  i obserwowanych + strony Nordnet z depeszami Direkt/TDN. Zapis: okna tekstu wokol trafien (raw/rekomendacje/*.txt,
  sha256 pliku i sha256 oryginalnej odpowiedzi w status.json) oraz wiersze z frazami o celach i ratingach
  (data/rekomendacje.csv) z data skopiowana z otoczenia wiersza bez interpretacji. Powod: 05.10.2026 poranny przebieg
  nie wykryl BofA 02.10 (cel 50 z 47) - publiczne listy w narzedziach modelu byly zamrozone.

Zasady (jak w ev-dane-pl):
- zadnych liczb wpisanych recznie; wszystko w data/ pochodzi z odpowiedzi zrodla albo z arytmetyki na nich
- kazdy pobrany plik ma w data/status.json: adres, czas UTC, kod HTTP, rozmiar, sha256
- blad jednego zrodla nie przerywa pozostalych; skrypt zawsze konczy sie zapisem status.json
- polaczenia wylacznie ze standardowymi ustawieniami bezpieczenstwa TLS
"""

import csv
import hashlib
import html
import io
import json
import re
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

WERSJA = "0.2.0"
DATA = Path("data")
RAW = DATA / "raw"
OSLO = ZoneInfo("Europe/Oslo")
UA = f"oslo-bors-dane/{WERSJA} (+https://github.com/Kozienice/oslo-bors-dane-)"
TIMEOUT = 60
PAUZA = 0.4  # sekundy miedzy zapytaniami do jednego serwera

PORTFEL = ["VAR", "NAS", "AFG", "TGS"]
OBSERWOWANE = ["BNOR"]
KLASTRY = {
    "ENERGIA": ["EQNR", "AKRBP"],
    "LOGISTYKA": ["MPCC", "HAUTO", "HAFNI", "FRO"],
    "PRZEMYSL": ["AKSO", "SUBC", "KOG"],
    "SEAFOOD": ["MOWI", "SALM", "LSG", "BAKKA"],
    "CRITICAL_MINERALS": ["NOM", "TEKNA", "NHY"],
    "BUDOWNICTWO": ["VEI", "SNTIA", "NRC"],
    "RADAR": ["POLAR", "GEM"],
}
TICKERY = PORTFEL + OBSERWOWANE + [t for lista in KLASTRY.values() for t in lista]
KURSY_TICKERY = PORTFEL + OBSERWOWANE + KLASTRY["ENERGIA"]
INDEKSY_YAHOO = {"OBX": "OBX.OL"}

NEWSWEB = "https://api3.oslo.oslobors.no/v1/newsreader"
DNI_LISTA = 14
DNI_TRESC = 7
# kategorie, dla ktorych pobieramy zalaczniki PDF (identyfikatory i nazwy z odpowiedzi API)
KATEGORIE_ZALACZNIKI = ("FLAGGING", "MAJOR SHAREHOLDINGS", "INSIDER", "MANAGERS' TRANSACTION",
                        "INSIDE INFORMATION", "MANDATORY NOTIFICATION")

teraz = datetime.now(timezone.utc)
status = {
    "uruchomienie_utc": teraz.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "uruchomienie_oslo": teraz.astimezone(OSLO).strftime("%Y-%m-%d %H:%M %Z"),
    "wersja_skryptu": WERSJA,
    "zrodla": {},
    "kontrole": {},
}


# ---------------------------------------------------------------- narzedzia

def sesja():
    s = requests.Session()
    s.headers["User-Agent"] = UA
    return s


def utc(dt=None):
    return (dt or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def zapisz(sciezka: Path, tresc: bytes, zrodlo: str, url: str, kod: int):
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    sciezka.write_bytes(tresc)
    status["zrodla"].setdefault(zrodlo, {}).setdefault("pliki", []).append({
        "plik": str(sciezka),
        "url": url,
        "http": kod,
        "bajty": len(tresc),
        "sha256": hashlib.sha256(tresc).hexdigest(),
        "pobrano_utc": utc(),
    })


def notuj(zrodlo: str, klucz: str, wartosc):
    status["zrodla"].setdefault(zrodlo, {})[klucz] = wartosc


def blad(zrodlo: str, opis: str):
    status["zrodla"].setdefault(zrodlo, {}).setdefault("bledy", []).append(opis[:500])


def get(s, url, zrodlo, params=None):
    try:
        r = s.get(url, params=params, timeout=TIMEOUT)
        pelny = r.url
        notuj(zrodlo, f"GET {pelny}", {"http": r.status_code, "bajty": len(r.content),
                                       "content_type": r.headers.get("Content-Type")})
        time.sleep(PAUZA)
        return r
    except Exception as e:
        blad(zrodlo, f"GET {url} {params or ''}: {type(e).__name__}: {e}")
        return None


def zapisz_csv(sciezka: Path, naglowek, wiersze):
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    with sciezka.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(naglowek)
        w.writerows(wiersze)


def oslo_czas(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(OSLO).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


# ---------------------------------------------------------------- newsweb

def newsweb(s):
    zr = "newsweb"
    od = (teraz - timedelta(days=DNI_LISTA)).strftime("%Y-%m-%d")
    do = (teraz + timedelta(days=1)).strftime("%Y-%m-%d")  # jutro, zeby nie uciac dzisiejszych
    granica_tresci = teraz - timedelta(days=DNI_TRESC)
    wiersze, liczniki, niepowodzenia = [], {}, []
    for t in TICKERY:
        r = get(s, f"{NEWSWEB}/list", zr, params={"issuer": t, "category": "", "fromDate": od, "toDate": do})
        if r is None or r.status_code != 200:
            niepowodzenia.append(t)
            continue
        zapisz(RAW / "newsweb" / "lista" / f"{t}.json", r.content, zr, r.url, r.status_code)
        try:
            j = r.json()
            h = j.get("header", {}) or {}
            # API zwraca klucze naglowka plasko ("result.text"), wersja zagniezdzona na wszelki wypadek
            ok = (h.get("result.text") or (h.get("result") or {}).get("text")) == "OK"
            msgs = j.get("data", {}).get("messages", []) or []
            if j.get("data", {}).get("overflow"):
                blad(zr, f"{t}: overflow=true (lista ucieta przez API)")
        except Exception as e:
            niepowodzenia.append(t)
            blad(zr, f"{t}: JSON {type(e).__name__}: {e}")
            continue
        if not ok:
            niepowodzenia.append(t)
        liczniki[t] = len(msgs)
        for m in msgs:
            kat = "; ".join(c.get("category_en", "") for c in m.get("category", []) or [])
            kat_no = "; ".join(c.get("category_no", "") for c in m.get("category", []) or [])
            pub = m.get("publishedTime", "")
            wiersze.append([t, m.get("messageId"), pub, oslo_czas(pub), m.get("title", ""), kat_no, kat,
                            m.get("issuerName", ""), m.get("numbAttachments", 0),
                            m.get("correctionForMessageId", 0), m.get("correctedByMessageId", 0),
                            f"{NEWSWEB}/message?messageId={m.get('messageId')}"])
            # tresc komunikatow z ostatnich 7 dni (pobierana raz, potem z repo)
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception:
                dt = teraz
            if dt >= granica_tresci:
                tresc(s, m, kat + " " + kat_no)
    wiersze.sort(key=lambda w: (w[2], w[0]), reverse=True)
    zapisz_csv(DATA / "komunikaty.csv",
               ["ticker", "messageId", "publishedTime_utc", "czas_oslo", "tytul", "kategoria_no", "kategoria_en",
                "emitent", "zalaczniki", "korekta_dla", "skorygowany_przez", "adres_tresci"], wiersze)
    status["kontrole"]["newsweb"] = {
        "tickery": len(TICKERY),
        "odpowiedzi_ok": len(TICKERY) - len(niepowodzenia),
        "niepowodzenia": niepowodzenia,
        "komunikaty_14_dni": len(wiersze),
        "per_ticker": liczniki,
        "okno": f"{od}..{do}",
        "wszystkie_ok": not niepowodzenia,
    }


def tresc(s, m, kategorie: str):
    zr = "newsweb_tresc"
    mid = m.get("messageId")
    plik = RAW / "newsweb" / "tresc" / f"{mid}.json"
    if plik.exists():
        return
    r = get(s, f"{NEWSWEB}/message", zr, params={"messageId": mid})
    if r is None or r.status_code != 200:
        blad(zr, f"{mid}: brak tresci")
        return
    zapisz(plik, r.content, zr, r.url, r.status_code)
    try:
        msg = r.json().get("data", {}).get("message", {}) or {}
        if msg.get("messageId") != mid:
            blad(zr, f"{mid}: messageId w odpowiedzi = {msg.get('messageId')}")
        if msg.get("body"):
            (RAW / "newsweb" / "tresc" / f"{mid}.txt").write_text(msg["body"], encoding="utf-8")
        if any(k in kategorie.upper() for k in KATEGORIE_ZALACZNIKI):
            for a in msg.get("attachments", []) or []:
                zalacznik(s, mid, a)
    except Exception as e:
        blad(zr, f"{mid}: {type(e).__name__}: {e}")


def zalacznik(s, mid, a):
    """EKSPERYMENTALNE: adres zalacznika nie jest udokumentowany; wynik (kod, typ, sygnatura) trafia do status.json."""
    zr = "newsweb_zalaczniki"
    aid, nazwa = a.get("id"), a.get("name", "")
    url = f"{NEWSWEB}/attachment"
    r = get(s, url, zr, params={"messageId": mid, "attachmentId": aid})
    if r is None or r.status_code != 200:
        return
    if not r.content.startswith(b"%PDF"):
        blad(zr, f"{mid}/{aid} {nazwa}: odpowiedz nie jest PDF ({r.headers.get('Content-Type')})")
        return
    sciezka = RAW / "newsweb" / "zalaczniki" / f"{mid}_{aid}.pdf"
    zapisz(sciezka, r.content, zr, r.url, r.status_code)
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(r.content)) as pdf:
            tekst = "\n\n".join((p.extract_text() or "") for p in pdf.pages)
        sciezka.with_suffix(".txt").write_text(tekst, encoding="utf-8")
    except Exception as e:
        blad(zr, f"{mid}/{aid}: tekst PDF {type(e).__name__}: {e}")


# ---------------------------------------------------------------- Norges Bank

def norges_bank(s):
    zr = "norges_bank"
    url = "https://data.norges-bank.no/api/data/EXR/B.USD+EUR+SEK.NOK.SP"
    r = get(s, url, zr, params={"format": "csv", "lastNObservations": 30, "locale": "en"})
    if r is None or r.status_code != 200:
        status["kontrole"]["norges_bank"] = {"ok": False}
        return
    zapisz(RAW / "norges_bank" / "exr.csv", r.content, zr, r.url, r.status_code)
    tekst = r.content.decode("utf-8-sig")
    rd = csv.DictReader(io.StringIO(tekst), delimiter=";" if tekst.count(";") > tekst.count(",") else ",")
    wiersze = []
    for w in rd:
        waluta = w.get("BASE_CUR") or w.get("Base Currency") or ""
        data = w.get("TIME_PERIOD") or w.get("Time Period") or ""
        wart = w.get("OBS_VALUE") or w.get("Observation Value") or ""
        mnoznik = w.get("UNIT_MULT") or w.get("Unit Multiplier") or ""
        if waluta and data:
            wiersze.append([data, waluta, wart, mnoznik])
    wiersze.sort()
    zapisz_csv(DATA / "waluty.csv", ["data", "waluta", "nok_za_jednostke_lub_100", "unit_mult"], wiersze)
    ostatnia = max((w[0] for w in wiersze), default="")
    status["kontrole"]["norges_bank"] = {"ok": bool(wiersze), "wierszy": len(wiersze), "ostatnia_data": ostatnia}


# ---------------------------------------------------------------- FRED

FRED_SERIE = {
    "DCOILBRENTEU": "Brent Europe spot FOB, dzienny (Dated Brent wg EIA)",
    "MCOILBRENTEU": "Brent Europe, srednia miesieczna",
    "PNGASEUUSDM": "Gaz ziemny UE, srednia miesieczna USD/MMBtu",
}


def fred(s):
    zr = "fred"
    wynik = {}
    for sid, opis in FRED_SERIE.items():
        url = "https://fred.stlouisfed.org/graph/fredgraph.csv"
        r = get(s, url, zr, params={"id": sid})
        if r is None or r.status_code != 200 or b"," not in r.content[:200]:
            wynik[sid] = {"ok": False}
            continue
        zapisz(RAW / "fred" / f"{sid}.csv", r.content, zr, r.url, r.status_code)
        rd = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
        obs = [(d, v) for d, v in rd[1:] if v not in ("", ".")]
        wynik[sid] = {"ok": bool(obs), "opis": opis, "ostatnia_data": obs[-1][0] if obs else "",
                      "ostatnia_wartosc": obs[-1][1] if obs else ""}
        zapisz_csv(DATA / "fred" / f"{sid}_ostatnie.csv", ["data", "wartosc"], obs[-90:])
    status["kontrole"]["fred"] = wynik


# ---------------------------------------------------------------- kursy (eksperymentalne)

def kursy(s):
    """Yahoo chart API - EKSPERYMENTALNE, klasa 4. Zadanie potwierdza kurs drugim zrodlem z data."""
    zr = "kursy_yahoo"
    wiersze, wynik = [], {}
    symbole = {t: f"{t}.OL" for t in KURSY_TICKERY}
    symbole.update(INDEKSY_YAHOO)
    for nazwa, sym in symbole.items():
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        r = get(s, url, zr, params={"range": "1mo", "interval": "1d"})
        if r is None or r.status_code != 200:
            wynik[nazwa] = {"ok": False, "http": getattr(r, "status_code", None)}
            continue
        zapisz(RAW / "kursy" / f"{nazwa}.json", r.content, zr, r.url, r.status_code)
        try:
            res = r.json()["chart"]["result"][0]
            ts = res.get("timestamp", []) or []
            q = res["indicators"]["quote"][0]
            meta = res.get("meta", {})
            n = 0
            for i, t in enumerate(ts):
                c = q.get("close", [None])[i]
                if c is None:
                    continue
                d = datetime.fromtimestamp(t, tz=timezone.utc).astimezone(OSLO).strftime("%Y-%m-%d")
                wiersze.append([nazwa, d, round(c, 4), q.get("volume", [None])[i], meta.get("currency", "")])
                n += 1
            ost = [w for w in wiersze if w[0] == nazwa]
            dzis_oslo = teraz.astimezone(OSLO)
            w_toku = bool(ost) and ost[-1][1] == dzis_oslo.strftime("%Y-%m-%d") and \
                (dzis_oslo.hour, dzis_oslo.minute) < (16, 30)
            wynik[nazwa] = {"ok": n > 0, "sesji": n, "ostatnia_sesja": ost[-1][1] if ost else "",
                            "ostatnie_zamkniecie": ost[-1][2] if ost else None,
                            "sesja_w_toku": w_toku,
                            "waluta": meta.get("currency", "")}
        except Exception as e:
            wynik[nazwa] = {"ok": False, "blad": f"{type(e).__name__}: {e}"[:200]}
    wiersze.sort(key=lambda w: (w[0], w[1]))
    zapisz_csv(DATA / "kursy.csv", ["ticker", "data_sesji_oslo", "zamkniecie", "wolumen", "waluta"], wiersze)
    status["kontrole"]["kursy_yahoo"] = {"eksperymentalne": True, "klasa": 4, "per_ticker": wynik}


# ---------------------------------------------------------------- rekomendacje brokerow (eksperymentalne)

# adresy stron z depeszami o celach i ratingach; slug-i skopiowane z wynikow wyszukiwania (05.10.2026)
MS = "https://www.marketscreener.com/quote/stock"
REKOMENDACJE_STRONY = {
    "VAR": [("marketscreener_broker", f"{MS}/VAR-ENERGI-133025650/news-broker-research/"),
            ("marketscreener_news", f"{MS}/VAR-ENERGI-133025650/news/")],
    "NAS": [("marketscreener_broker", f"{MS}/NORWEGIAN-AIR-SHUTTLE-ASA-1413204/news-broker-research/"),
            ("marketscreener_news", f"{MS}/NORWEGIAN-AIR-SHUTTLE-ASA-1413204/news/")],
    "AFG": [("marketscreener_broker", f"{MS}/AF-GRUPPEN-ASA-1413069/news-broker-research/"),
            ("marketscreener_news", f"{MS}/AF-GRUPPEN-ASA-1413069/news/")],
    "TGS": [("marketscreener_broker", f"{MS}/TGS-ASA-1413301/news-broker-research/"),
            ("marketscreener_news", f"{MS}/TGS-ASA-1413301/news/"),
            ("nordnet_fi", "https://www.nordnet.fi/markkinakatsaus/osakekurssit/16105575-tgs-asa")],
    "BNOR": [("marketscreener_broker", f"{MS}/BLUENORD-ASA-1413217/news-broker-research/"),
             ("marketscreener_news", f"{MS}/BLUENORD-ASA-1413217/news/"),
             ("nordnet_se", "https://www.nordnet.se/aktier/kurser/blue-nord-bnor-xosl")],
}
# frazy o celach i ratingach: EN, SV, NO, FI, DE
REK_WZOR = re.compile(
    r"(target|price objective|rating|upgrad|downgrad|initiat|coverage|riktkurs|kursm[aå]l|kursmaal|anbefal|"
    r"oppgrader|nedgrader|h[oö]jer|s[aä]nker|tavoitehin|suositus|kursziel)", re.I)
DATA_WZORY = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2})?"),
    re.compile(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b"),
    re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? \d{1,2}\b"),
    re.compile(r"\b\d{1,2}\.? (?:jan|feb|mar|apr|mai|maj|may|jun|jul|aug|sep|okt|oct|nov|des|dec)[a-z]*\b", re.I),
    re.compile(r"\b\d{1,2}\.? (?:tammi|helmi|maalis|huhti|touko|kes[aä]|hein[aä]|elo|syys|loka|marras|joulu)\w*"
               r"(?: \d{1,2}[.:]\d{2})?", re.I),
    re.compile(r"\b\d{1,2}/\d{1,2}\b"),
    re.compile(r"\b\d{1,2}:\d{2}(?:am|pm)?\b", re.I),
]


def tekst_strony(html_bytes: bytes) -> str:
    """HTML -> linie tekstu bez znacznikow; tresc skryptow zostaje (strony Next.js trzymaja depesze w JSON)."""
    t = html_bytes.decode("utf-8", errors="replace")
    t = re.sub(r"(?is)<style.*?</style>", "\n", t)
    t = re.sub(r"(?s)<[^>]+>", "\n", t)
    t = html.unescape(t)
    t = re.sub(r"\\u([0-9a-fA-F]{4})",
               lambda m: chr(int(m.group(1), 16)) if not 0xD800 <= int(m.group(1), 16) <= 0xDFFF else "", t)
    t = t.replace('\\"', '"').replace("\\n", "\n").replace("\\/", "/")
    t = re.sub(r'","|\},\{|\],\[', "\n", t)
    linie = [re.sub(r"\s+", " ", l).strip() for l in t.split("\n")]
    return "\n".join(l for l in linie if l)


# klucze tlumaczen interfejsu (np. 'PAGE_INSTRUMENT.ANALYST_RATINGS...":"') to szum, nie depesze
SZUM_UI = re.compile(r'^"?[A-Z0-9_]+(\.[A-Z0-9_]+)+"')


def data_z_otoczenia(linie, i, najpierw_nizej=False):
    """Pierwszy napis wygladajacy na date: w wierszu, potem do 3 wierszy wyzej i do 6 nizej (Nordnet podaje date
    pod naglowkiem, wiec tam najpierw nizej). Kopiowany 1:1, bez interpretacji."""
    wyzej = list(range(i - 1, max(i - 4, -1), -1))
    nizej = list(range(i + 1, min(i + 7, len(linie))))
    kolejnosc = [i] + (nizej + wyzej if najpierw_nizej else wyzej + nizej)
    for j in kolejnosc:
        if len(linie[j]) > 400:
            continue
        for w in DATA_WZORY:
            m = w.search(linie[j])
            if m:
                return m.group(0)
    return ""


def rekomendacje(s):
    zr = "rekomendacje"
    wiersze, wynik = [], {}
    for t, strony in REKOMENDACJE_STRONY.items():
        for nazwa, url in strony:
            klucz = f"{t}/{nazwa}"
            r = get(s, url, zr)
            if r is None or r.status_code != 200:
                wynik[klucz] = {"ok": False, "http": getattr(r, "status_code", None)}
                continue
            linie = tekst_strony(r.content).split("\n")
            widziane, n, okna = set(), 0, []
            for i, l in enumerate(linie):
                if not (15 <= len(l) <= 400) or not REK_WZOR.search(l) or SZUM_UI.search(l) or l in widziane:
                    continue
                widziane.add(l)
                wiersze.append([t, nazwa, data_z_otoczenia(linie, i, nazwa.startswith("nordnet")), l, r.url, utc()])
                okna.append("\n".join(x for x in linie[max(i - 3, 0):i + 7] if len(x) <= 400))
                n += 1
            # zapisujemy tylko okna wokol trafien (strona ma do 1 MB tekstu); pelna odpowiedz potwierdza sha256
            plik = RAW / "rekomendacje" / f"{t}_{nazwa}.txt"
            zapisz(plik, "\n----\n".join(okna).encode("utf-8", "replace"), zr, r.url, r.status_code)
            wpis = status["zrodla"][zr]["pliki"][-1]
            wpis["bajty_odpowiedzi"] = len(r.content)
            wpis["sha256_odpowiedzi"] = hashlib.sha256(r.content).hexdigest()
            wynik[klucz] = {"ok": True, "http": r.status_code, "bajty": len(r.content), "trafien": n}
    zapisz_csv(DATA / "rekomendacje.csv",
               ["ticker", "zrodlo", "data_w_otoczeniu", "wiersz", "adres", "pobrano_utc"], wiersze)
    status["kontrole"]["rekomendacje"] = {"eksperymentalne": True, "klasa": "do ustalenia (RELAY po weryfikacji)",
                                          "stron": sum(len(v) for v in REKOMENDACJE_STRONY.values()),
                                          "ok": sum(1 for w in wynik.values() if w.get("ok")),
                                          "wierszy": len(wiersze), "per_strona": wynik}


# ---------------------------------------------------------------- podsumowanie dla zadania

def podsumowanie():
    k = status["kontrole"]
    linie = [f"# Oslo Bors - dane z {status['uruchomienie_oslo']} (skrypt {WERSJA})", "",
             "Plik wygenerowany automatycznie z danych w tym repozytorium. Zadnej liczby nie wpisano recznie.", ""]
    nw = k.get("newsweb", {})
    linie.append(f"- API newsweb: {nw.get('odpowiedzi_ok', 0)}/{nw.get('tickery', 0)} tickerow OK, "
                 f"{nw.get('komunikaty_14_dni', 0)} komunikatow w oknie {nw.get('okno', '')}; "
                 f"niepowodzenia: {', '.join(nw.get('niepowodzenia', [])) or 'brak'}")
    nb = k.get("norges_bank", {})
    linie.append(f"- Norges Bank: {'OK' if nb.get('ok') else 'BLAD'}, ostatnia data {nb.get('ostatnia_data', '')}")
    for sid, w in (k.get("fred") or {}).items():
        linie.append(f"- FRED {sid}: {'OK' if w.get('ok') else 'BLAD'} {w.get('ostatnia_data', '')} "
                     f"{w.get('ostatnia_wartosc', '')}")
    ky = (k.get("kursy_yahoo") or {}).get("per_ticker", {})
    ok = [f"{t} {w.get('ostatnie_zamkniecie')} ({w.get('ostatnia_sesja')}{', sesja w toku' if w.get('sesja_w_toku') else ''})"
          for t, w in ky.items() if w.get("ok")]
    zle = [t for t, w in ky.items() if not w.get("ok")]
    linie.append(f"- Kursy Yahoo (eksperymentalne, klasa 4): {'; '.join(ok) or 'brak'}; bledy: {', '.join(zle) or 'brak'}")
    rk = k.get("rekomendacje") or {}
    zle_r = [n for n, w in (rk.get("per_strona") or {}).items() if not w.get("ok")]
    linie.append(f"- Rekomendacje (eksperymentalne): {rk.get('ok', 0)}/{rk.get('stron', 0)} stron OK, "
                 f"{rk.get('wierszy', 0)} wierszy w rekomendacje.csv; bledy: {', '.join(zle_r) or 'brak'}")
    linie += ["", "Pliki: komunikaty.csv, rekomendacje.csv, waluty.csv, kursy.csv, fred/*_ostatnie.csv, raw/ (surowe odpowiedzi), status.json"]
    (DATA / "podsumowanie.md").write_text("\n".join(linie) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- start

def main():
    DATA.mkdir(exist_ok=True)
    s = sesja()
    for krok in (newsweb, norges_bank, fred, kursy, rekomendacje):
        try:
            krok(s)
        except Exception:
            blad("skrypt", f"{krok.__name__}: {traceback.format_exc()[-800:]}")
    status["zakonczenie_utc"] = utc()
    try:
        podsumowanie()
    except Exception:
        blad("skrypt", f"podsumowanie: {traceback.format_exc()[-800:]}")
    (DATA / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
