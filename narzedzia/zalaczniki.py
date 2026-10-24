"""zalaczniki.py - pobranie na zadanie tresci i zalacznikow PDF wskazanych komunikatow newsweb (tickery spoza oslo.py).
Wejscie: narzedzia/zalaczniki_lista.txt (jeden messageId w linii, '#' = komentarz).
Wyjscie: data/raw/newsweb/tresc/{mid}.json|.txt, data/raw/newsweb/zalaczniki/{mid}_{aid}.pdf|.txt,
         data/raw/newsweb/zalaczniki_na_zadanie.json (adres, czas UTC, kod HTTP, bajty, sha256 kazdego pliku).
Zasady jak w oslo.py: zadnych liczb wpisanych recznie, standardowy TLS, blad jednego pliku nie przerywa reszty."""
import hashlib, io, json, time
from datetime import datetime, timezone
from pathlib import Path
import requests

NEWSWEB = "https://api3.oslo.oslobors.no/v1/newsreader"
RAW = Path("data/raw/newsweb")
UA = "oslo-bors-dane/zalaczniki (+https://github.com/Kozienice/oslo-bors-dane-)"
log = {"uruchomienie_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "pliki": [], "bledy": []}

def zapisz(p, b, url, kod):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b)
    log["pliki"].append({"plik": str(p), "url": url, "http": kod, "bajty": len(b),
                         "sha256": hashlib.sha256(b).hexdigest(),
                         "pobrano_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})

s = requests.Session(); s.headers["User-Agent"] = UA
ids = [l.split("#")[0].strip() for l in Path("narzedzia/zalaczniki_lista.txt").read_text().splitlines()]
for mid in [i for i in ids if i]:
    try:
        r = s.get(f"{NEWSWEB}/message", params={"messageId": mid}, timeout=60); time.sleep(0.4)
        if r.status_code != 200:
            log["bledy"].append(f"{mid}: message HTTP {r.status_code}"); continue
        zapisz(RAW / "tresc" / f"{mid}.json", r.content, r.url, r.status_code)
        msg = r.json().get("data", {}).get("message", {}) or {}
        if str(msg.get("messageId")) != mid:
            log["bledy"].append(f"{mid}: messageId w odpowiedzi = {msg.get('messageId')}")
        if msg.get("body"):
            (RAW / "tresc" / f"{mid}.txt").write_text(msg["body"], encoding="utf-8")
        for a in msg.get("attachments", []) or []:
            aid = a.get("id")
            ra = s.get(f"{NEWSWEB}/attachment", params={"messageId": mid, "attachmentId": aid}, timeout=60); time.sleep(0.4)
            if ra.status_code != 200 or not ra.content.startswith(b"%PDF"):
                log["bledy"].append(f"{mid}/{aid} {a.get('name')}: HTTP {ra.status_code} {ra.headers.get('Content-Type')}"); continue
            p = RAW / "zalaczniki" / f"{mid}_{aid}.pdf"
            zapisz(p, ra.content, ra.url, ra.status_code)
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(ra.content)) as pdf:
                    t = "\n\n".join((pg.extract_text() or "") for pg in pdf.pages)
                p.with_suffix(".txt").write_text(f"# {a.get('name')}\n" + t, encoding="utf-8")
            except Exception as e:
                log["bledy"].append(f"{mid}/{aid}: tekst PDF {type(e).__name__}: {e}")
    except Exception as e:
        log["bledy"].append(f"{mid}: {type(e).__name__}: {e}")
(RAW / "zalaczniki_na_zadanie.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"pliki": len(log["pliki"]), "bledy": log["bledy"]}, ensure_ascii=False))
