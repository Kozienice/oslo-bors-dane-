"""Jednorazowa sonda: co portale NO udostepniaja publicznie (robots.txt, RSS, sitemapy news). Wynik: sonda/."""
import json, re, time, hashlib
from pathlib import Path
import requests

UA = "oslo-bors-dane/sonda (+https://github.com/Kozienice/oslo-bors-dane-)"
OUT = Path("sonda"); OUT.mkdir(exist_ok=True)
DOMENY = {
    "dn": "https://www.dn.no", "e24": "https://e24.no", "finansavisen": "https://www.finansavisen.no",
    "nordnet": "https://www.nordnet.no", "estatenyheter": "https://www.estatenyheter.no", "tu": "https://www.tu.no",
}
KANDYDACI = ["/robots.txt", "/rss", "/rss/", "/rss.xml", "/feed", "/rss2/", "/sitemap.xml", "/sitemap-news.xml",
             "/sitemap_news.xml", "/news-sitemap.xml", "/sitemaps/news.xml", "/"]
s = requests.Session(); s.headers["User-Agent"] = UA
wynik = {}
for nazwa, baza in DOMENY.items():
    wynik[nazwa] = {}
    urls = [baza + k for k in KANDYDACI]
    for url in list(urls):
        try:
            r = s.get(url, timeout=30); time.sleep(1.0)
        except Exception as e:
            wynik[nazwa][url] = {"blad": str(e)[:200]}; continue
        b = r.content
        typ = r.headers.get("Content-Type", "")
        info = {"http": r.status_code, "bajty": len(b), "typ": typ, "final": r.url}
        if r.status_code == 200 and len(b) < 3_000_000:
            fn = OUT / f"{nazwa}_{hashlib.md5(url.encode()).hexdigest()[:8]}.txt"
            fn.write_bytes(b[:400_000]); info["plik"] = str(fn)
            t = b[:400_000].decode("utf-8", "replace")
            info["rss_items"] = t.count("<item")
            info["sitemap_urls"] = t.count("<url>") + t.count("<sitemap>")
            info["news_publication_date"] = t.count("publication_date")
            info["ld_json"] = len(re.findall(r'application/ld\+json', t))
            if url.endswith("robots.txt"):
                sm = re.findall(r'(?im)^\s*sitemap:\s*(\S+)', t)
                info["sitemapy"] = sm[:20]
                for u in sm[:8]:
                    if u not in urls:
                        urls.append(u)
                        try:
                            r2 = s.get(u, timeout=30); time.sleep(1.0)
                            t2 = r2.content[:400_000].decode("utf-8", "replace")
                            fn2 = OUT / f"{nazwa}_{hashlib.md5(u.encode()).hexdigest()[:8]}.txt"
                            fn2.write_bytes(r2.content[:400_000])
                            wynik[nazwa][u] = {"http": r2.status_code, "bajty": len(r2.content), "typ": r2.headers.get("Content-Type", ""),
                                               "plik": str(fn2), "sitemap_urls": t2.count("<url>") + t2.count("<sitemap>"),
                                               "news_publication_date": t2.count("publication_date"), "rss_items": t2.count("<item")}
                        except Exception as e:
                            wynik[nazwa][u] = {"blad": str(e)[:200]}
        wynik[nazwa][url] = info
(OUT / "wynik.json").write_text(json.dumps(wynik, ensure_ascii=False, indent=1))
