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

WERSJA 0.7.0 (2026-10-24) - bufor bezpieczenstwa (decyzja uzytkownika 24.10.2026: repo publiczne = tylko dane pochodne)
- Nordnet: nazwy uzytkownikow, id profili, awatary, opisy profili, kraj i daty dolaczenia nie trafiaja do repo.
- Surowych kopii stron i kanalow nie zapisujemy: raw/prasa/* i raw/rekomendacje/*.txt znikaja; w status.json
  zostaje adres, kod HTTP, rozmiar i sha256 odpowiedzi (sekcja "odpowiedzi").
- prasa.csv bez kolumny lead (lead i opis z kanalu sluza tylko do dopasowania slow kluczowych w trakcie przebiegu);
  dodane slowa kluczowe fuzji (MA, CONOCO, ENI, AKER_TRG) dla obserwacji VAR/AKRBP.
- Kontrola autorow na koncu przebiegu: plik w data/ ze sladem danych profilu jest usuwany i opisany w status.json.
- Ten sam dzien: krok rekomendacji (MarketScreener + Nordnet, w tym forum) WYLACZONY - regulaminy obu zrodel zabraniaja
  automatycznego pobierania i redystrybucji; data/rekomendacje.csv usuniety (szczegoly przy REKOMENDACJE_WLACZONE).
- Ten sam dzien, decyzje wlasciciela: rezygnacja z forum Nordnet (kod forum i adresy stron Nordnet usuniete);
  kursy Yahoo WYLACZONE - warunki Yahoo zabraniaja automatycznego zbierania danych i ich rozpowszechniania
  (data/kursy.csv i data/raw/kursy usuniete; szczegoly przy KURSY_WLACZONE).

Zasady (jak w ev-dane-pl):
- zadnych liczb wpisanych recznie; wszystko w data/ pochodzi z odpowiedzi zrodla albo z arytmetyki na nich
- kazdy pobrany plik ma w data/status.json: adres, czas UTC, kod HTTP, rozmiar, sha256
- blad jednego zrodla nie przerywa pozostalych; skrypt zawsze konczy sie zapisem status.json
- polaczenia wylacznie ze standardowymi ustawieniami bezpieczenstwa TLS
"""

import csv
import gzip
from email.utils import parsedate_to_datetime
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

WERSJA = "0.7.0"
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


def odpowiedz_bez_pliku(zrodlo: str, tresc: bytes, url: str, kod: int):
    """Slad pobrania bez zapisu surowej kopii do publicznego repo: adres, kod, rozmiar i sha256 odpowiedzi."""
    status["zrodla"].setdefault(zrodlo, {}).setdefault("odpowiedzi", []).append({
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

# WYLACZONE 24.10.2026 (bufor bezpieczenstwa, decyzja wlasciciela): warunki Yahoo
# https://legal.yahoo.com/xw/en/yahoo/terms/otos/index.html - sekcja 2(d) pkt 9 zakazuje zbierania danych z uslug
# "using any automated means", sekcja 2(h) zakazuje reprodukcji i dystrybucji tresci i API bez pisemnej zgody.
# Wlaczenie z powrotem tylko decyzja wlasciciela repo.
KURSY_WLACZONE = False


def kursy(s):
    """Yahoo chart API - EKSPERYMENTALNE, klasa 4. Zadanie potwierdza kurs drugim zrodlem z data."""
    zr = "kursy_yahoo"
    if not KURSY_WLACZONE:
        status["kontrole"]["kursy_yahoo"] = {"wylaczone": True, "od": "2026-10-24",
                                             "powod": "warunki Yahoo zabraniaja automatycznego zbierania danych i ich "
                                                      "rozpowszechniania (bufor bezpieczenstwa)"}
        return
    wiersze, wynik = [], {}
    symbole = {t: f"{t}.OL" for t in KURSY_TICKERY}
    symbole.update(INDEKSY_YAHOO)
    for nazwa, sym in symbole.items():
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
        r = get(s, url, zr, params={"range": "1y", "interval": "1d"})
        if r is None or r.status_code != 200:
            wynik[nazwa] = {"ok": False, "http": getattr(r, "status_code", None)}
            continue
        zapisz(RAW / "kursy" / f"{nazwa}.json", r.content, zr, r.url, r.status_code)
        try:
            res = r.json()["chart"]["result"][0]
            ts = res.get("timestamp", []) or []
            q = res["indicators"]["quote"][0]
            meta = res.get("meta", {})
            n, z_meta = 0, False
            # rano Yahoo zwraca ostatnia sesje z close=None (07-08.10.2026, PB-118/PB-121), a zamkniecie
            # jest w meta.regularMarketPrice z regularMarketTime po aukcji zamkniecia (16:20 Oslo)
            rmt, rmp = meta.get("regularMarketTime"), meta.get("regularMarketPrice")
            meta_d, meta_po_zamknieciu = "", False
            if rmt and rmp is not None:
                mt = datetime.fromtimestamp(rmt, tz=timezone.utc).astimezone(OSLO)
                meta_d, meta_po_zamknieciu = mt.strftime("%Y-%m-%d"), (mt.hour, mt.minute) >= (16, 20)
            for i, t in enumerate(ts):
                c = q.get("close", [None])[i]
                d = datetime.fromtimestamp(t, tz=timezone.utc).astimezone(OSLO).strftime("%Y-%m-%d")
                if c is None:
                    if i == len(ts) - 1 and d == meta_d and meta_po_zamknieciu:
                        c, z_meta = rmp, True
                    else:
                        continue
                wiersze.append([nazwa, d, round(c, 4), q.get("volume", [None])[i], meta.get("currency", "")])
                n += 1
            ost = [w for w in wiersze if w[0] == nazwa]
            dzis_oslo = teraz.astimezone(OSLO)
            w_toku = bool(ost) and ost[-1][1] == dzis_oslo.strftime("%Y-%m-%d") and \
                (dzis_oslo.hour, dzis_oslo.minute) < (16, 30)
            wynik[nazwa] = {"ok": n > 0, "sesji": n, "ostatnia_sesja": ost[-1][1] if ost else "",
                            "ostatnie_zamkniecie": ost[-1][2] if ost else None,
                            "sesja_w_toku": w_toku,
                            "ostatnie_zamkniecie_z_meta": z_meta,
                            "waluta": meta.get("currency", "")}
        except Exception as e:
            wynik[nazwa] = {"ok": False, "blad": f"{type(e).__name__}: {e}"[:200]}
    wiersze.sort(key=lambda w: (w[0], w[1]))
    zapisz_csv(DATA / "kursy.csv", ["ticker", "data_sesji_oslo", "zamkniecie", "wolumen", "waluta"], wiersze)
    status["kontrole"]["kursy_yahoo"] = {"eksperymentalne": True, "klasa": 4, "per_ticker": wynik}


# ---------------------------------------------------------------- rekomendacje brokerow (eksperymentalne)

# WYLACZONE 24.10.2026 (bufor bezpieczenstwa): warunki obu zrodel zabraniaja automatycznego pobierania i redystrybucji:
# Nordnet - https://www.nordnet.se/faq/ovrigt/regler-foer-scraping-och-automatisk-datainsamling ("under inga omstandigheter"
# skrapa data, niezaleznie od celu, takze do analizy prywatnej; publikacja i redystrybucja zabronione bez umowy);
# MarketScreener - https://www.marketscreener.com/navigation/contrat-4T.htm art. 4 (zakaz reprodukcji i redystrybucji,
# pobieranie tylko w osobistym, ograniczonym w czasie uzytku). Robots.txt obu nie blokuje tych sciezek, ale regulamin tak.
# Wlaczenie z powrotem tylko decyzja wlasciciela repo. Forum Nordnet: rezygnacja wlasciciela 24.10.2026 (adresy usuniete).
REKOMENDACJE_WLACZONE = False
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
            ("marketscreener_news", f"{MS}/TGS-ASA-1413301/news/")],
    "BNOR": [("marketscreener_broker", f"{MS}/BLUENORD-ASA-1413217/news-broker-research/"),
             ("marketscreener_news", f"{MS}/BLUENORD-ASA-1413217/news/")],
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


# ---------------------------------------------------------------- bufor: dane profili autorow nie trafiaja do repo

# linie z blokow profilu (Shareville na stronach Nordnet): id profilu, nazwa, awatar, opis, slug, kraj, data dolaczenia
LINIA_PROFILU = re.compile(r'^(profile":\{"id"|"?(username|userName|displayName|firstName|lastName|avatarUri|avatarUrl|'
                           r'description|slug|country)"\s*:|"?rating":.*joinedAt|.*"joinedAt":)')
# slad danych profilu w pliku = plik usuwany przed commitem (kontrola_autorow)
SLAD_AUTORA = re.compile(r'(username"+\s*:|avatarUri|avatarUrl|shareville-media|joinedAt"+\s*:|profile"+:\{"+id"+)', re.I)
WZMIANKA = re.compile(r"@[\w.\-]+")


def nazwy_autorow(linie):
    """Nazwy i slugi profili ze strony - do podmiany na 'xxx' tam, gdzie wystepuja jako zwykly tekst."""
    t = "\n".join(linie)
    nazwy = set(re.findall(r'(?:username|userName|displayName|slug)":"([^"\n]{3,40})', t))
    return sorted(nazwy, key=len, reverse=True)


def zamaskuj(tekst, nazwy):
    tekst = WZMIANKA.sub("@xxx", tekst)
    for n in nazwy:
        tekst = re.sub(r"(?<![\w])" + re.escape(n) + r"(?![\w])", "xxx", tekst, flags=re.I)
    return tekst


def bez_profili(linie, nazwy=()):
    return [zamaskuj(l, nazwy) for l in linie if not LINIA_PROFILU.search(l) and "shareville-media" not in l]


def kontrola_autorow():
    """Ostatni krok przed zapisem status.json: plik w data/ ze sladem danych profilu jest usuwany (nie trafi do commita)."""
    usuniete = []
    for p in sorted(DATA.rglob("*")):
        if not p.is_file() or p.name == "status.json" or p.suffix not in (".csv", ".txt", ".md", ".json", ".xml", ".html"):
            continue
        try:
            if SLAD_AUTORA.search(p.read_text(encoding="utf-8", errors="replace")):
                p.unlink()
                usuniete.append(str(p))
        except Exception as e:
            blad("kontrola_autorow", f"{p}: {type(e).__name__}: {e}")
    status["kontrole"]["autorzy"] = {"ok": not usuniete, "usuniete_pliki": usuniete,
                                     "zasada": "w repo zadnych danych o autorach wpisow (nazwa, id profilu, awatar, opis, kraj)"}


def rekomendacje(s):
    zr = "rekomendacje"
    if not REKOMENDACJE_WLACZONE:
        status["kontrole"]["rekomendacje"] = {"wylaczone": True, "od": "2026-10-24",
                                              "powod": "regulaminy Nordnet i MarketScreener zabraniaja automatycznego "
                                                       "pobierania i redystrybucji (bufor bezpieczenstwa)"}
        return
    wiersze, wynik = [], {}
    for t, strony in REKOMENDACJE_STRONY.items():
        for nazwa, url in strony:
            klucz = f"{t}/{nazwa}"
            r = get(s, url, zr)
            if r is None or r.status_code != 200:
                wynik[klucz] = {"ok": False, "http": getattr(r, "status_code", None)}
                continue
            surowe = tekst_strony(r.content).split("\n")
            nazwy = nazwy_autorow(surowe)
            linie = bez_profili(surowe, nazwy)
            widziane, n = set(), 0
            for i, l in enumerate(linie):
                if not (15 <= len(l) <= 400) or not REK_WZOR.search(l) or SZUM_UI.search(l) or l in widziane:
                    continue
                widziane.add(l)
                wiersze.append([t, nazwa, data_z_otoczenia(linie, i, nazwa.startswith("nordnet")), l, r.url, utc()])
                n += 1
            # bez surowej kopii strony w repo: zostaje slad pobrania (adres, kod, rozmiar, sha256 odpowiedzi)
            odpowiedz_bez_pliku(zr, r.content, r.url, r.status_code)
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
    kyk = k.get("kursy_yahoo") or {}
    if kyk.get("wylaczone"):
        linie.append(f"- Kursy Yahoo: WYLACZONE od {kyk.get('od')} - {kyk.get('powod')}")
    else:
        ky = kyk.get("per_ticker", {})
        ok = [f"{t} {w.get('ostatnie_zamkniecie')} ({w.get('ostatnia_sesja')}{', sesja w toku' if w.get('sesja_w_toku') else ''})"
              for t, w in ky.items() if w.get("ok")]
        zle = [t for t, w in ky.items() if not w.get("ok")]
        linie.append(f"- Kursy Yahoo (eksperymentalne, klasa 4): {'; '.join(ok) or 'brak'}; bledy: {', '.join(zle) or 'brak'}")
    rk = k.get("rekomendacje") or {}
    if rk.get("wylaczone"):
        linie.append(f"- Rekomendacje (MarketScreener): WYLACZONE od {rk.get('od')} - {rk.get('powod')}")
    else:
        zle_r = [n for n, w in (rk.get("per_strona") or {}).items() if not w.get("ok")]
        linie.append(f"- Rekomendacje (eksperymentalne): {rk.get('ok', 0)}/{rk.get('stron', 0)} stron OK, "
                     f"{rk.get('wierszy', 0)} wierszy w rekomendacje.csv; bledy: {', '.join(zle_r) or 'brak'}")
    sh = k.get("shorty") or {}
    linie.append(f"- Shorty Finanstilsynet (klasa 1): {'OK' if sh.get('ok') else 'BLAD'}, {sh.get('z_pozycjami', 0)} spolek z pozycjami, "
                 f"{sh.get('aktywnych_pozycji', 0)} aktywnych pozycji, ostatnie zdarzenie {sh.get('ostatnia_data', '')}")
    pr = k.get("prasa") or {}
    linie.append(f"- Prasa (kanaly RSS i mapy artykulow, tytul + data + adres): {'OK' if pr.get('ok') else 'BLAD'}, "
                 f"{pr.get('wierszy_w_pliku', 0)} naglowkow w prasa.csv ({pr.get('z_trafieniami', 0)} z trafieniami); w kanalach: {pr.get('pozycji_w_kanalach', {})}")
    au = k.get("autorzy") or {}
    linie.append(f"- Kontrola autorow: {'OK' if au.get('ok') else 'USUNIETO PLIKI: ' + ', '.join(au.get('usuniete_pliki', []))}")
    linie += ["", "Pliki: prasa.csv, komunikaty.csv, waluty.csv, shorty.csv, shorty_pozycje.csv, shorty_historia.csv, fred/*_ostatnie.csv, raw/ (odpowiedzi zrodel danych: newsweb, Norges Bank, FRED, Finanstilsynet), status.json"]
    (DATA / "podsumowanie.md").write_text("\n".join(linie) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- shorty (Finanstilsynet, klasa 1)

SSR = "https://ssr.finanstilsynet.no/api/v2/instruments"
SHORTY_DNI = 120


def shorty(s):
    """Rejestr krotkich pozycji Finanstilsynet (publikowane pozycje >= 0,5% kapitalu, aktualizacja w dni sesyjne ok. 15:30).
    Surowa odpowiedz: data/raw/finanstilsynet/instruments.json.gz; pochodne: shorty.csv (ostatni stan kazdej spolki),
    shorty_pozycje.csv (aktywne pozycje z ostatniego zdarzenia), shorty_historia.csv (zdarzenia z ostatnich SHORTY_DNI dni)."""
    zr = "shorty"
    r = get(s, SSR, zr)
    if r is None or r.status_code != 200:
        status["kontrole"]["shorty"] = {"ok": False, "http": getattr(r, "status_code", None)}
        return
    notuj(zr, "sha256_odpowiedzi", hashlib.sha256(r.content).hexdigest())
    zapisz(RAW / "finanstilsynet" / "instruments.json.gz", gzip.compress(r.content, mtime=0), zr, r.url, r.status_code)
    dane = r.json()
    if isinstance(dane, dict):
        dane = dane.get("instruments") or dane.get("items") or list(dane.values())
    granica = (datetime.now(timezone.utc) - timedelta(days=SHORTY_DNI)).strftime("%Y-%m-%d")
    stan, pozycje, historia = [], [], []
    for ins in dane:
        isin, emitent = ins.get("isin", ""), ins.get("issuerName", "")
        zd = sorted(ins.get("events") or [], key=lambda e: str(e.get("date", "")))
        for e in zd:
            if str(e.get("date", ""))[:10] >= granica:
                historia.append([isin, emitent, str(e.get("date", ""))[:10], e.get("shortPercent", ""), e.get("shares", ""),
                                 len(e.get("activePositions") or [])])
        if not zd:
            continue
        ost = zd[-1]
        akt = ost.get("activePositions") or []
        stan.append([isin, emitent, str(ost.get("date", ""))[:10], ost.get("shortPercent", ""), ost.get("shares", ""), len(akt)])
        for p in akt:
            pozycje.append([isin, emitent, str(ost.get("date", ""))[:10], p.get("positionHolder", ""),
                            p.get("shortPercent", ""), p.get("shares", ""), str(p.get("date", ""))[:10]])
    stan.sort(key=lambda w: w[1])
    pozycje.sort(key=lambda w: (w[1], -float(w[4] or 0)))
    historia.sort(key=lambda w: (w[1], w[2]))
    zapisz_csv(DATA / "shorty.csv", ["isin", "emitent", "data_ostatniego_zdarzenia", "short_proc_lacznie", "akcje", "pozycji"], stan)
    zapisz_csv(DATA / "shorty_pozycje.csv", ["isin", "emitent", "data_zdarzenia", "posiadacz", "short_proc", "akcje", "data_pozycji"], pozycje)
    zapisz_csv(DATA / "shorty_historia.csv", ["isin", "emitent", "data", "short_proc_lacznie", "akcje", "pozycji"], historia)
    ost_data = max((w[2] for w in stan), default="")
    status["kontrole"]["shorty"] = {"ok": bool(stan), "klasa": 1, "instrumentow": len(dane), "z_pozycjami": len(stan),
                                    "aktywnych_pozycji": len(pozycje), "ostatnia_data": ost_data}


# ---------------------------------------------------------------- prasa NO - tytul, data, lead z kanalow publicznych

# Zrodla wybrane po sondzie 06.10.2026 (narzedzia/sonda.py): tylko portale, ktore publikuja kanal RSS albo mape strony
# i nie zabraniaja automatycznego przetwarzania. POMINIETE CELOWO: dn.no (robots.txt: scraping, monitoring mediow i
# ekstrakcja danych wymagaja umowy; blokada botow AI) i e24.no (warunki RSS i robots.txt zabraniaja uzycia tresci jako
# wejscia dla LLM i automatycznego przetwarzania bez zgody).
PRASA_RSS = {
    "bygg": "https://www.bygg.no/?lab_viewport=rss",
    "anlegg": "https://anlegg.bygg.no/?lab_viewport=rss",
    "estate": "https://www.estatenyheter.no/?lab_viewport=rss",
    "tu": "https://www.tu.no/?lab_viewport=rss",
    # sonda 3 (07.10.2026): robots.txt bez blokady botow AI i bez zakazu, kanal RSS z data
    "shifter": "https://www.shifter.no/?lab_viewport=rss",
    "kyst": "https://www.kyst.no/?lab_viewport=rss",
    "ilaks": "https://ilaks.no/feed/",
    "offshore_energy": "https://www.offshore-energy.biz/feed",
    "anleggsmaskinen": "https://anleggsmaskinen.no/feed/",
    "vegvesen": "https://www.vegvesen.no/rss",
    # sonda 5 (07.10.2026): robots.txt bez blokady botow AI i bez zakazu, kanal RSS z data
    "boligprodusentene": "https://www.boligprodusentene.no/rss",
    "investornytt": "https://www.investornytt.no/?lab_viewport=rss",
    "energiogklima": "https://www.energiogklima.no/rss.xml",
    "byggmesteren": "https://byggmesteren.as/feed/",
    "fishfarmingexpert": "https://www.fishfarmingexpert.com/?lab_viewport=rss",
    "gcaptain": "https://gcaptain.com/feed/",
    "hellenic_shipping": "https://www.hellenicshippingnews.com/feed/",  # robots.txt Crawl-delay 30 - jedno zapytanie na przebieg
    "northernminer": "https://www.northernminer.com/feed/",
}
# mapy news (news:title + news:publication_date), robots.txt bez zakazu
PRASA_NEWS_SITEMAP = {"offshore_mag": "https://www.offshore-mag.com/sitemap-google-news.xml"}
# POMINIETE po sondach 3 i 5 (robots.txt blokuje boty AI lub zabrania scrapingu/ekstrakcji): energiwatch.no, europower.no,
# intrafish.no, investtech.com, nettavisen.no, nrk.no, tradewindsnews.com, upstreamonline.com, aftenposten.no, vg.no, tv2.no,
# aksjelive.no (E24), borsen.dk, di.se, kauppalehti.fi, placera.se, oilprice.com; niedostepne (403): mining.com, splash247.com
PRASA_ANGIELSKIE = {"offshore_energy", "fishfarmingexpert", "gcaptain", "hellenic_shipping", "northernminer", "offshore_mag"}
PRASA_FA_SITEMAP = "https://ws.finansavisen.no/sitemap/sitemap-articles-{rok}-{mies}.xml"  # robots.txt: Crawl-delay 10
PRASA_DNI = 60
# slowa kluczowe -> ticker lub temat (tytul, lead i adres, bez rozrozniania wielkosci liter)
PRASA_KLUCZE = {
    "VAR": [r"vår energi", r"var energi"], "TGS": [r"\btgs\b"],
    "NAS": [r"norwegian air", r"norwegian-(sjef|konsern|aksje)", r"\bnorwegians\b", r"widerøe", r"\bnas\b"],
    "BNOR": [r"bluenord"], "EQNR": [r"equinor"], "AKRBP": [r"aker bp"],
    "AFG": [r"\bAF[- ]?(gruppen|selskap|anlegg|bygg|decom|energi|dotter)\b", r"\bAF\b", r"betonmast", r"\bmepas\b", r"stad[- ]skipstunnel"],
    "VEI": [r"veidekke"], "SNTIA": [r"\bhent\b", r"sentia"], "NRC": [r"\bnrc\b"],
    "NOM": [r"nordic mining", r"engebø", r"førdefjord"], "NHY": [r"\bhydro\b"], "TEKNA": [r"\btekna\b"],
    "FEN": [r"fensfelt", r"rare earths norway", r"sjeldne jordarter"],
    "OBOS": [r"\bobos\b"], "SKANSKA": [r"skanska"], "NCC": [r"\bncc\b"], "PEAB": [r"\bpeab\b"], "CONSTO": [r"consto"],
    "BOLIGSALG": [r"boligprodusent", r"nye boliger", r"boligsalg"], "RENTE": [r"norges bank", r"styringsrent"],
    "FRAKT": [r"\bvlcc\b", r"tanker rates?", r"freight rates?", r"\bsuezmax\b", r"\baframax\b", r"baltic (dry|exchange)"],
    "KRYT_MIN": [r"rare earths?", r"critical (raw )?minerals?", r"kritiske mineral", r"sjeldne jordarter"],
    "KONKURS": [r"konkurs"], "TVIST": [r"tvist|forlik|søksmål|stevning|rettssak"],
    # obserwacja hipotezy fuzji VAR/AKRBP (zadania PORTFEL i PIATEK, pkt FUZJA): dopasowanie na tytule i opisie z kanalu,
    # bo opisu nie zapisujemy w repo (0.7.0)
    "MA": [r"fusjon", r"sammensl[åa]", r"oppkj[øo]p", r"\bmerger\b", r"\bcombination\b"],
    "CONOCO": [r"conoco"], "ENI": [r"\beni\b"], "AKER_TRG": [r"aker asa", r"\btrg\b"],
}


def tekst_xml(t: str) -> str:
    t = re.sub(r"(?s)<!\[CDATA\[(.*?)\]\]>", r"\1", t or "")
    return html.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\u00ad", "").strip()


def prasa(s):
    """Naglowki prasy NO: tytul, data publikacji i adres z kanalow RSS i z map artykulow (Finansavisen, offshore-mag).
    Tresci artykulow NIE pobieramy - jedno zapytanie na portal na przebieg. Akumulacja w data/prasa.csv (60 dni).
    Od 0.7.0 bez leadu i bez surowych kopii kanalow w repo: opis z kanalu sluzy tylko do dopasowania slow kluczowych."""
    zr = "prasa"
    plik = DATA / "prasa.csv"
    pola = ["id", "portal", "opublikowano_utc", "czas_oslo", "pluss", "tytul", "trafienia", "adres"]
    wiersze, opisy, stare_traf = {}, {}, {}
    if plik.exists():
        for w in csv.DictReader(plik.open(encoding="utf-8")):
            if w.get("tytul") and w.get("portal"):
                wiersze[w["id"]] = {p_: w.get(p_, "") for p_ in pola}
                stare_traf[w["id"]] = (w.get("trafienia") or "").split()
    na_portal = {}
    for portal, url in PRASA_RSS.items():
        r = None
        for proba in range(2):
            time.sleep(3 if proba == 0 else 20)  # wiele portali stoi na jednym CMS (Labrador) - nie zasypujemy serwera
            r = get(s, url, zr)
            if r is not None and r.status_code == 200 and (b"<item" in r.content or b"<entry" in r.content):
                break
        if r is None or r.status_code != 200 or not (b"<item" in r.content or b"<entry" in r.content):
            poczatek = (r.content[:160].decode("utf-8", "replace") if r is not None else "").replace("\n", " ")
            blad(zr, f"{portal}: HTTP {getattr(r, 'status_code', None)}, brak <item>; poczatek: {poczatek}")
            na_portal[portal] = 0
            continue
        odpowiedz_bez_pliku(zr, r.content, r.url, r.status_code)
        n = 0
        tresc = r.content.decode("utf-8", "replace")
        atom = "<entry" in tresc and "<item" not in tresc
        for it in re.findall(r"(?s)<entry[ >](.*?)</entry>" if atom else r"(?s)<item>(.*?)</item>", tresc):
            pole = lambda t: tekst_xml((re.search(r"(?s)<%s(?:\s[^>]*)?>(.*?)</%s>" % (t, t), it) or [None, ""])[1])
            if atom:
                link = html.unescape((re.search(r'<link[^>]*href="([^"]+)"', it) or [None, ""])[1])
                tyt = pole("title")
            else:
                link, tyt = pole("link"), pole("title")
            if not (link and tyt):
                continue
            m = re.search(r"/(\d{5,})(?:\?|/?$)", link)
            klucz = m.group(1) if m else hashlib.sha256(link.split("?")[0].encode()).hexdigest()[:12]
            try:
                if atom:
                    pub = utc(datetime.fromisoformat((pole("published") or pole("updated")).replace("Z", "+00:00")).astimezone(timezone.utc))
                else:
                    pub = utc(parsedate_to_datetime(pole("pubDate")).astimezone(timezone.utc))
            except Exception:
                pub = ""
            aid = f"{portal}:{klucz}"
            wiersze[aid] = {"id": aid, "portal": portal, "opublikowano_utc": pub, "czas_oslo": oslo_czas(pub) if pub else "",
                            "pluss": "tak" if ("/pluss/" in link or tyt.startswith("(+)")) else "",
                            "tytul": tyt.removeprefix("(+)").strip(), "trafienia": "", "adres": link}
            opisy[aid] = pole("summary") if atom else pole("description")
            n += 1
        na_portal[portal] = n
    # Finansavisen: mapa artykulow biezacego miesiaca (+ poprzedniego w pierwszych 3 dniach)
    teraz_ = datetime.now(timezone.utc)
    miesiace = [(teraz_.year, teraz_.month)]
    if teraz_.day <= 3:
        pm = teraz_.replace(day=1) - timedelta(days=1)
        miesiace.append((pm.year, pm.month))
    n = 0
    for rok, mies in miesiace:
        url = PRASA_FA_SITEMAP.format(rok=rok, mies=mies)
        r = get(s, url, zr)
        time.sleep(10)  # Crawl-delay z robots.txt Finansavisen
        if r is None or r.status_code != 200:
            blad(zr, f"finansavisen {rok}-{mies}: HTTP {getattr(r, 'status_code', None)}")
            continue
        odpowiedz_bez_pliku(zr, r.content, r.url, r.status_code)
        for u in re.findall(r"(?s)<url>(.*?)</url>", r.content.decode("utf-8", "replace")):
            loc = tekst_xml((re.search(r"<loc>(.*?)</loc>", u) or [None, ""])[1])
            tyt = tekst_xml((re.search(r"(?s)<news:title>(.*?)</news:title>", u) or [None, ""])[1])
            pub = tekst_xml((re.search(r"<news:publication_date>(.*?)</news:publication_date>", u) or [None, ""])[1])
            m = re.search(r"/(\d{6,})/", loc)
            if not (m and tyt):
                continue
            pub = pub.replace(".000Z", "Z")
            aid = f"finansavisen:{m.group(1)}"
            wiersze[aid] = {"id": aid, "portal": "finansavisen", "opublikowano_utc": pub, "czas_oslo": oslo_czas(pub) if pub else "",
                            "pluss": "", "tytul": tyt, "trafienia": "", "adres": loc}
            opisy.setdefault(aid, "")
            n += 1
    na_portal["finansavisen"] = n
    for portal, url in PRASA_NEWS_SITEMAP.items():
        time.sleep(3)
        r = get(s, url, zr)
        if r is None or r.status_code != 200 or b"<news:title" not in r.content:
            blad(zr, f"{portal}: HTTP {getattr(r, 'status_code', None)}, brak news:title")
            na_portal[portal] = 0
            continue
        odpowiedz_bez_pliku(zr, r.content, r.url, r.status_code)
        n = 0
        for u in re.findall(r"(?s)<url>(.*?)</url>", r.content.decode("utf-8", "replace")):
            loc = tekst_xml((re.search(r"<loc>(.*?)</loc>", u) or [None, ""])[1])
            tyt = tekst_xml((re.search(r"(?s)<news:title>(.*?)</news:title>", u) or [None, ""])[1])
            pub = tekst_xml((re.search(r"<news:publication_date>(.*?)</news:publication_date>", u) or [None, ""])[1])
            if not (loc and tyt):
                continue
            try:
                pub = utc(datetime.fromisoformat(pub.replace("Z", "+00:00")).astimezone(timezone.utc))
            except Exception:
                pub = ""
            aid = f"{portal}:{hashlib.sha256(loc.encode()).hexdigest()[:12]}"
            wiersze[aid] = {"id": aid, "portal": portal, "opublikowano_utc": pub, "czas_oslo": oslo_czas(pub) if pub else "",
                            "pluss": "", "tytul": tyt, "trafienia": "", "adres": loc}
            opisy.setdefault(aid, "")
            n += 1
        na_portal[portal] = n
    for aid, w in wiersze.items():
        tekst = f"{w['tytul']} {opisy.get(aid, '')} {w['adres']}"
        if w["portal"] not in PRASA_ANGIELSKIE:  # w tekstach norweskich samo 'Norwegian' to prawie zawsze linia lotnicza
            tekst += " norwegian-aksje" if re.search(r"\bnorwegian\b(?! cruise)", tekst, re.I) else ""
        traf = [k for k, wz in PRASA_KLUCZE.items() if any(re.search(x, tekst, re.I) for x in wz)]
        if aid not in opisy:  # pozycja spoza dzisiejszych kanalow: opisu juz nie ma, trafienia z niego zostaja z pliku
            traf += [k for k in stare_traf.get(aid, []) if k not in traf]
        w["trafienia"] = " ".join(traf)
    granica = (teraz_ - timedelta(days=PRASA_DNI)).strftime("%Y-%m-%d")
    lista = [w for w in wiersze.values() if (w.get("opublikowano_utc") or "9999") >= granica]
    lista.sort(key=lambda w: (w.get("opublikowano_utc") or "", w["id"]), reverse=True)
    zapisz_csv(plik, pola, [[w.get(p_, "") for p_ in pola] for w in lista])
    status["kontrole"]["prasa"] = {"ok": any(na_portal.values()), "pozycji_w_kanalach": na_portal, "wierszy_w_pliku": len(lista),
                                   "z_trafieniami": sum(1 for w in lista if w.get("trafienia")),
                                   "najnowszy": lista[0]["opublikowano_utc"] if lista else "",
                                   "pominiete_celowo": "dn.no, e24.no (warunki portali zabraniaja automatycznego przetwarzania)",
                                   "zapis": "tytul, data, adres, trafienia; bez leadu i bez surowych kopii kanalow (0.7.0)"}


# ---------------------------------------------------------------- start

def main():
    DATA.mkdir(exist_ok=True)
    s = sesja()
    for krok in (newsweb, norges_bank, fred, kursy, rekomendacje, shorty, prasa):
        try:
            krok(s)
        except Exception:
            blad("skrypt", f"{krok.__name__}: {traceback.format_exc()[-800:]}")
    status["zakonczenie_utc"] = utc()
    try:
        kontrola_autorow()
    except Exception:
        blad("skrypt", f"kontrola_autorow: {traceback.format_exc()[-800:]}")
    try:
        podsumowanie()
    except Exception:
        blad("skrypt", f"podsumowanie: {traceback.format_exc()[-800:]}")
    (DATA / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
