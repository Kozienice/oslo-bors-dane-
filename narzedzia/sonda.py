"""Sonda portali NO: robots.txt (zakazy dla botow AI i scrapingu), kanaly RSS i mapy news. Zapisuje TYLKO podsumowanie
(sonda/wynik4.json) - bez kopii stron."""
import json, re, time
from pathlib import Path
import requests

UA = "oslo-bors-dane/sonda (+https://github.com/Kozienice/oslo-bors-dane-)"
OUT = Path("sonda"); OUT.mkdir(exist_ok=True)
DOMENY = ["https://www.placera.se", "https://www.di.se", "https://www.kauppalehti.fi", "https://www.hegnar.no",
          "https://www.investornytt.no", "https://www.minerva.no", "https://www.aksjelive.no", "https://www.nordnet.no/blogg",
          "https://www.borsen.dk", "https://kommunikasjon.ntb.no", "https://www.mynewsdesk.com", "https://www.banenor.no",
          "https://www.inderes.no", "https://www.byggeindustrien.no", "https://www.byggmesteren.as", "https://www.mtbeoffshore.no",
          "https://www.sysla.no", "https://www.energiogklima.no", "https://www.e24.no", "https://www.mining.com",
          "https://www.northernminer.com", "https://www.fishfarmingexpert.com", "https://www.splash247.com", "https://gcaptain.com",
          "https://www.hellenicshippingnews.com", "https://www.offshore-mag.com", "https://www.oilprice.com", "https://www.aftenposten.no",
          "https://www.vg.no", "https://www.tv2.no", "https://www.estatenyheter.no", "https://www.boligprodusentene.no"]
RSS = ["/?lab_viewport=rss", "/rss", "/rss.xml", "/feed", "/feed/", "/rss/", "/rss/nyheter", "/api/feed/rss/", "/nyheter/rss"]
ZAKAZ = re.compile(r"(?i)(scrap|crawl|data extraction|text and data mining|TDM|tekst- og datautvinning|datautvinning|"
                   r"large language|LLM|artificial intelligence|kunstig intelligens|\bAI\b|media monitoring|medieovervåk)")
BOTY = re.compile(r"(?i)user-agent:\s*(anthropic-ai|claudebot|claude-web|gptbot|ccbot)")
wynik = {}
class Odp:
    pass
def pobierz(s, url, limit=300_000, czas=12):
    """GET z limitem bajtow i calkowitego czasu (serwery potrafia saczyc dane bez konca)."""
    t0 = time.time()
    r = s.get(url, timeout=(5, 5), stream=True)
    buf = b""
    for kaw in r.iter_content(16384):
        buf += kaw
        if len(buf) >= limit or time.time() - t0 > czas:
            break
    r.close()
    o = Odp(); o.status_code = r.status_code; o.url = r.url; o.content = buf; o.text = buf.decode("utf-8", "replace")
    time.sleep(0.3)
    return o
def zapisz_czastkowo():
    (OUT / "wynik4.json").write_text(json.dumps(wynik, ensure_ascii=False, indent=1))
def sonduj(baza):
    print("start", baza, flush=True)
    s = requests.Session(); s.headers["User-Agent"] = UA
    d = {}
    try:
        r = pobierz(s, baza.split("/blogg")[0] + "/robots.txt")
        t = r.text if r.status_code == 200 else ""
        d["robots_http"] = r.status_code
        d["robots_blokuje_boty_ai"] = bool(BOTY.search(t))
        d["robots_uwagi"] = sorted(set(m.group(0).lower() for m in ZAKAZ.finditer("\n".join(l for l in t.splitlines() if l.strip().startswith("#")))))[:8]
        d["robots_disallow_all"] = bool(re.search(r"(?ims)^user-agent:\s*\*\s*$(?:\n(?!user-agent).*)*?^disallow:\s*/\s*$", t))
        d["crawl_delay"] = (re.search(r"(?im)^crawl-delay:\s*(\S+)", t) or [None, None])[1]
        d["sitemapy"] = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", t)[:6]
    except Exception as e:
        d["robots_blad"] = str(e)[:120]
    d["rss"] = {}
    t_start = time.time()
    for k in RSS:
        if time.time() - t_start > 90:
            d["rss_przerwane"] = True
            break
        url = baza.rstrip("/") + k
        try:
            r = pobierz(s, url)
        except Exception as e:
            continue
        t = r.content[:300000].decode("utf-8", "replace")
        n = t.count("<item") + t.count("<entry")
        if r.status_code == 200 and n:
            opis = (re.search(r"(?s)<channel>.*?<description>(.*?)</description>", t) or [None, ""])[1][:600]
            tyt = [re.sub(r"<!\[CDATA\[|\]\]>", "", x).strip()[:90] for x in re.findall(r"(?s)<item>.*?<title>(.*?)</title>", t)[:2]]
            d["rss"][url] = {"final": r.url, "pozycji": n, "pubDate": t.count("<pubDate") + t.count("<published") + t.count("<updated"),
                             "opis_zakaz": sorted(set(m.group(0).lower() for m in ZAKAZ.finditer(opis))), "przyklad": tyt}
            break
    wynik[baza] = d
    zapisz_czastkowo()
    print("gotowe", baza, flush=True)

from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(16) as ex:
    list(ex.map(sonduj, DOMENY))
(OUT / "wynik4.json").write_text(json.dumps(wynik, ensure_ascii=False, indent=1))
