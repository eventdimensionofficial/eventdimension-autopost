"""Legge il sito Event Dimension e aggiorna events.csv (eventi nuovi, date, locandine, link).

Uso: python sync_events.py            (scarica il sito)
     python sync_events.py file.html  (usa pagine già scaricate, per prove)
"""
import csv, html, os, re, sys, urllib.request
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "events.csv")
FIELDS = ["slug", "name", "sub", "date", "venue", "link", "image", "when"]
SITES = [s.strip() for s in os.environ.get("SITE_URLS", "https://eventdimension.com,https://test.eventdimension.com").split(",") if s.strip()]
PAGES = ["/", "/club", "/festival"]
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def clean(t):
    return html.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\xa0", " ").strip()


def parse(page):
    """Le card evento: <article ... aspect-[3/4]> con locandina, alt "Locandina di NOME – CITTÀ, 21 novembre 2026", luogo e link."""
    out = []
    for art in re.findall(r"<article[^>]*aspect-\[3/4\].*?</article>", page, re.S):
        img = re.search(r'<img[^>]+src="([^"]+/storage/events/[^"]+)"', art)
        alt = re.search(r'alt="Locandina di ([^"]+)"', art)
        h3 = re.search(r"<h3[^>]*>\s*<a[^>]+href=\"([^\"]+)\"[^>]*>(.*?)</a>", art, re.S)
        loc = re.search(r'<p[^>]*uppercase[^>]*>.*?<span class="truncate">(.*?)</span>', art, re.S)
        if not (img and alt and h3):
            continue
        a = html.unescape(alt.group(1))
        m = re.search(r"(\d{1,2}) (" + "|".join(MESI) + r") (\d{4})\s*$", a)
        if not m:
            continue
        when = date(int(m.group(3)), MESI.index(m.group(2)) + 1, int(m.group(1)))
        img_url = re.sub(r"-480(\.\w+)$", r"\1", img.group(1))
        out.append({"image": img_url, "link": h3.group(1), "name": clean(h3.group(2)),
                    "venue": clean(loc.group(1)) if loc else "", "when": when.isoformat(),
                    "stem": os.path.splitext(os.path.basename(img_url))[0]})
    return out


def label(when, today):
    d = date.fromisoformat(when)
    s = f"{d.day} {MESI[d.month - 1].upper()}"
    return s + (f" {d.year}" if d.year != today.year and (d - today).days > 120 else "")


def slugify(stem):
    s = re.sub(r"-(terminal-1-co-cinecitta-world)$", "-roma", stem)
    s = re.sub(r"-presents-.*", "", s) if len(s) > 40 else s
    return s[:50].strip("-")


def main():
    today = date.today()
    pages = []
    if len(sys.argv) > 1:
        pages = [open(p, encoding="utf-8").read() for p in sys.argv[1:]]
    else:
        for base in SITES:
            got = []
            for p in PAGES:
                try:
                    got.append(fetch(base.rstrip("/") + p))
                except Exception as e:
                    print("non raggiungibile:", base + p, e)
            if any(parse(g) for g in got):
                pages = got
                print("::notice::sito usato:", base)
                break
    found = {}
    for pg in pages:
        for ev in parse(pg):
            found.setdefault(ev["stem"], ev)
    if not found:
        print("Nessun evento letto dal sito: events.csv non cambia.")
        return 0
    rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
    for r in rows:
        for f in FIELDS:
            r.setdefault(f, "")
    by_stem = {}
    for r in rows:
        st = os.path.splitext(os.path.basename(r.get("image") or ""))[0]
        if st:
            by_stem[st] = r
    by_link = {r["link"].rstrip("/"): r for r in rows if r.get("link")}
    changes = []
    for st, ev in found.items():
        r = by_stem.get(st) or by_link.get(ev["link"].rstrip("/"))
        if r is None:
            slug = slugify(st)
            while any(x["slug"] == slug for x in rows):
                slug += "-2"
            r = {"slug": slug, "name": ev["name"].title() if ev["name"].isupper() else ev["name"], "sub": "",
                 "date": label(ev["when"], today), "venue": ev["venue"], "link": ev["link"],
                 "image": ev["image"], "when": ev["when"]}
            rows.append(r)
            changes.append(f"NUOVO {slug} · {r['date']} · {r['venue']}")
            continue
        if r.get("when") != ev["when"]:
            if r.get("when"):
                r["date"] = label(ev["when"], today)
            changes.append(f"data {r['slug']}: {r.get('when')} → {ev['when']}")
            r["when"] = ev["when"]
        if r.get("image") != ev["image"]:
            changes.append(f"locandina {r['slug']}")
            r["image"] = ev["image"]
        # i link dei club restano quelli di vendita; per i festival si passa al sito online appena disponibile
        if r.get("link") != ev["link"] and "test." not in ev["link"]:
            changes.append(f"link {r['slug']}")
            r["link"] = ev["link"]
    rows.sort(key=lambda r: r.get("when") or "9999")
    with open(CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    nuovi = [c[6:] for c in changes if c.startswith("NUOVO ")]
    topic = os.environ.get("NTFY_TOPIC")
    if nuovi and topic:
        import json
        msg = {"topic": topic, "title": f"🆕 {len(nuovi)} evento/i nuovo/i sul sito",
               "message": "\n".join(nuovi) + "\nPreparo grafiche e notifiche in automatico.", "tags": ["tada"]}
        try:
            urllib.request.urlopen(urllib.request.Request(os.environ.get("NTFY_SERVER", "https://ntfy.sh"),
                                   data=json.dumps(msg).encode(), headers={"Content-Type": "application/json"}), timeout=20)
        except Exception as e:
            print("notifica non inviata:", e)
    print(f"::notice::Eventi sul sito: {len(found)}. Modifiche: {len(changes)}")
    for c in changes:
        print(" -", c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
