"""Pianificatore automatico: tiene SEMPRE pronte le notifiche dei prossimi giorni.

Per ogni giorno da oggi a oggi+DAYS che non ha ancora promemoria storie (id "s-MMGG-*"),
crea il piano del giorno a partire da events.csv (solo eventi futuri con grafiche pronte):
  - 5 storie (11:30, 14:00, 18:00, 20:30, 22:30) con musica suggerita
  - controllo profili 13:00 ogni giorno
  - post: mar, gio, dom 19:00 · sab 18:30 (+ ricondividi 30 min dopo)
  - reel nostri: lun, mer 19:30
  - reel di altri da ripubblicare: mer, ven, sab 21:30
  - novità da postare: lun, mer, ven 17:00
  - "domani c'è…": 16:00 il giorno prima di ogni serata
Le righe già presenti (anche scritte a mano o dal piano settimanale) non vengono toccate.
"""
import csv, os, sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Europe/Rome")
DAYS = int(os.environ.get("PLAN_DAYS", "7"))
FIELDS = ["id", "datetime", "type", "media", "caption", "status", "result", "note"]
MEDIA = os.path.join(HERE, "media")
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
EXTRA = ['sondaggio "Ci sei? 🔥 Sì / Ovvio"', "countdown all'evento", 'domanda "Con chi vieni? 👇"',
         'cursore emoji 🔥 "Quanto sei carico?"', 'sondaggio "Prima volta o veterano?"',
         'quiz "Indovina l\'orario del set"', 'domanda "Che pezzo vuoi sentire? 🎧"']


def is_fest(e):
    return "eventi/" in e["link"] or e["when"] >= f"{date.today().year + 1}" and "ticketdimension" not in e["link"]


def music(e):
    n = (e["name"] + " " + e["sub"]).lower()
    if "xmas" in n or "christmas" in n or "rizardo" in n:
        return "house / funky house natalizia"
    if any(k in n for k in ("carola", "sosa", "sdk", "jamback", "loto", "koko")):
        return "tech house / minimal groove"
    if any(k in n for k in ("traumer", "seggio")):
        return "minimal / deep tech"
    if is_fest(e):
        return "anthem del festival / techno da main stage"
    return "techno / tech house di tendenza"


def tag(s):
    return "#" + "".join(ch for ch in s.title() if ch.isalnum())


def nice(e):
    return e["name"], e["date"].title().replace(" · ", "-"), e["venue"].replace(" · ", ", ")


def has(kind, slug):
    return os.path.exists(os.path.join(MEDIA, f"{kind}-{slug}.{'mp4' if kind == 'reel' else 'jpg'}"))


def load():
    evs = [e for e in csv.DictReader(open(os.path.join(HERE, "events.csv"), encoding="utf-8")) if e.get("when")]
    cal = list(csv.DictReader(open(os.path.join(HERE, "calendar.csv"), encoding="utf-8")))
    return evs, cal


def main():
    evs, cal = load()
    ids = {r["id"] for r in cal}
    today = datetime.now(TZ).date()
    now_s = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    new = []

    def add(id_, dt, cap, media=""):
        if id_ in ids or dt <= now_s:
            return
        ids.add(id_)
        new.append({"id": id_, "datetime": dt, "type": "REMINDER", "media": media, "caption": cap,
                    "status": "scheduled", "result": "", "note": "auto"})

    def recent(prefix, slug, day, n):
        lo = (day - timedelta(days=n)).isoformat()
        return any(r["id"].startswith(prefix) and slug in r["media"] and lo <= r["datetime"][:10] <= day.isoformat()
                   for r in cal + new)

    for i in range(DAYS + 1):
        day = today + timedelta(days=i)
        md = f"{day:%m%d}"
        if any(r["id"].startswith(f"s-{md}-") for r in cal + new):
            continue      # giorno già pianificato
        ds = day.isoformat()
        up = sorted([e for e in evs if e["when"] >= ds and has("storia", e["slug"] + "-link")], key=lambda e: e["when"])
        if not up:
            continue
        clubs = [e for e in up if not is_fest(e)]
        fests = [e for e in up if is_fest(e)]
        # --- storie: pesi in base a quanto manca all'evento
        def w(e):
            d = (date.fromisoformat(e["when"]) - day).days
            return 8 if d == 0 else 6 if d <= 3 else 4 if d <= 7 else 2 if d <= 21 else 1
        pool = sorted(clubs[:6], key=w, reverse=True)
        picks, credit = [], {e["slug"]: 0.0 for e in pool}
        for _ in range(4 if fests else 5):
            if not pool:
                break
            for e in pool:
                credit[e["slug"]] += w(e)
            best = max(pool, key=lambda e: (credit[e["slug"]] - (5 if picks and picks[-1]["slug"] == e["slug"] else 0)))
            credit[best["slug"]] -= sum(w(e) for e in pool)
            picks.append(best)
        if fests:
            picks.insert(3, fests[day.toordinal() % min(len(fests), 6)])
        while len(picks) < 5 and up:
            picks.append(up[len(picks) % len(up)])
        for n, (t, e) in enumerate(zip(["11:30", "14:00", "18:00", "20:30", "22:30"], picks), 1):
            name, d, v = nice(e)
            today_ev = e["when"] == ds
            extra = '"STASERA 🔥" + countdown' if today_ev else EXTRA[(day.toordinal() + n) % len(EXTRA)]
            add(f"s-{md}-{n}", f"{ds} {t}",
                f"📲 Storia da pubblicare: {name} · {'STASERA' if today_ev else d}, {v}\n"
                "1) Salva l'immagine  2) Instagram → nuova storia\n"
                f"3) Sticker LINK: {e['link']}\n4) Extra: {extra}\n🎵 Aggiungi la MUSICA: {music(e)}",
                f"storia-{e['slug']}-link.jpg")
        # --- controllo profili
        add(f"c-{md}", f"{ds} 13:00", "🔎 Controlla i profili degli eventi e dei club del sito\n"
            "Guarda se hanno pubblicato post, reel o storie nuove.\n"
            "Se c'è qualcosa → Condividi → \"Aggiungi alla storia\" + sticker LINK ai biglietti + tag del profilo\n"
            "https://www.instagram.com/")
        wd = day.weekday()
        # --- post
        if wd in (1, 3, 5, 6):
            t = "18:30" if wd == 5 else "19:00"
            if wd == 6 and len(fests) >= 2:
                sel = [e for e in fests if has("post", e["slug"]) and not recent("p-", e["slug"], day, 30)][:3]
                if len(sel) < 2:
                    sel = fests[:3]
                media = "|".join(f"post-{e['slug']}.jpg" for e in sel)
                lines = "\n".join(f"• {e['name']} · {e['date'].title()}, {e['venue'].split('·')[-1].strip()}" for e in sel)
                cap = (f"✈️ FESTIVAL: si parte!\n\n{lines}\n\nBiglietti, pacchetti hotel e bus su eventdimension.com 🔗 link in bio\n"
                       f"Quale non puoi perderti? 👇\n\n{' '.join(tag(e['name'].split(' 20')[0]) for e in sel)} #festival #techno #eventdimension")
                title = "Festival"
            else:
                cand = [e for e in clubs if has("post", e["slug"]) and e["when"] > ds and not recent("p-", e["slug"], day, 10)]
                if not cand:
                    cand = [e for e in clubs if has("post", e["slug"]) and e["when"] > ds]
                if not cand:
                    cand = []
                sel = cand[:1]
                if sel:
                    e = sel[0]; name, d, v = nice(e)
                    gg = (date.fromisoformat(e["when"]) - day).days
                    quando = "DOMANI" if gg == 1 else f"tra {gg} giorni"
                    media = f"post-{e['slug']}.jpg"
                    cap = (f"🔥 {name.upper()}\n{d} · {v}\n\n{('Una notte da non perdere: ' + e['sub'] + '. ') if e['sub'] and e['sub'].lower() not in (name + e['venue']).lower() and len(e['sub']) > 6 else ''}"
                           f"Si balla {quando} ⏳\n\n🎟️ Biglietti su eventdimension.com · link in bio\n\n"
                           f"{tag(name.split('·')[0].split(' at ')[0].split('+')[0])} {tag(v.split(',')[0])} {tag(v.split(',')[-1])} #clubbing #techno #nightlife #eventdimension")
                    title = name
            if sel:
                n = len(sel)
                steps = (f"1) Salva le {n} immagini (tasti Immagine)  2) Instagram → nuovo post (seleziona più foto)" if n > 1
                         else "1) Salva l'immagine  2) Instagram → nuovo post")
                add(f"p-{md}", f"{ds} {t}", f"📸 {'Carosello' if n > 1 else 'Post'} da pubblicare: {title}\n{steps}\n3) Copia questa descrizione:\n\n{cap}", media)
                h, m = map(int, t.split(":")); m += 30; h += m // 60; m %= 60
                add(f"rp-{md}", f"{ds} {h:02d}:{m:02d}", f"🔁 Ricondividi il post nelle storie: {title}\n"
                    "1) Apri il post → tasto Condividi → \"Aggiungi alla storia\"\n"
                    "2) Sticker LINK ai biglietti + testo \"NUOVO POST 👀\"\n🎵 Aggiungi la MUSICA\n"
                    "https://www.instagram.com/eventdimension_experience/")
        # --- reel nostri
        if wd in (0, 2):
            cand = [e for e in clubs if has("reel", e["slug"]) and e["when"] > ds and not recent("r-", e["slug"], day, 10)] or \
                   [e for e in up if has("reel", e["slug"])]
            if cand:
                e = cand[0]; name, d, v = nice(e)
                add(f"r-{md}", f"{ds} 19:30", f"🎬 Reel da pubblicare: {name} · {d}, {v}\n"
                    "1) Salva il video (tasto Video)  2) Instagram → nuovo Reel\n"
                    f"3) Aggiungi un AUDIO DI TENDENZA ({music(e)})\n4) Descrizione:\n\n"
                    f"🔥 {name} · {d} · {v}\n🎟️ Link in bio\n{tag(name.split('·')[0].split('+')[0])} #eventdimension", f"reel-{e['slug']}.mp4")
        # --- reel di altri
        if wd in (2, 4, 5) and clubs:
            e = clubs[0]
            club = e["venue"].split("·")[0].strip()
            gg = (date.fromisoformat(e["when"]) - day).days
            txt = '"STASERA 🔥"' if gg == 0 else f'"{e["date"].title()} 🔥 chi c\'è?"'
            add(f"x-{md}", f"{ds} 21:30", f"🔁 Ripubblica nelle storie un reel di {club} o di {e['name']}\n"
                f"1) Cerca {club} su Instagram → apri l'ultimo reel\n2) Condividi → \"Aggiungi alla storia\"\n"
                f"3) Sticker LINK: {e['link']} + tag del profilo\n4) Testo: {txt}\nhttps://www.instagram.com/")
        # --- novità
        if wd in (0, 2, 4):
            hint = ", ".join(e["name"] for e in clubs[:3]) or "festival in vendita"
            add(f"n-{md}", f"{ds} 17:00", "📰 Novità da postare? Controlla sito e social degli eventi\n"
                "Cerca: lineup aggiornate, orari (set times), mappe, sold out / ultimi biglietti, nuovi eventi, aftermovie.\n"
                "Se c'è qualcosa → fai un POST o una STORIA, es.:\n• \"LINEUP COMPLETA 🔥\" + locandina nuova\n"
                f"• \"ULTIMI BIGLIETTI ⚠️\" / \"SOLD OUT\"\n• \"ORARI DEI SET ⏰\"\n👉 Occhio a: {hint}\nhttps://eventdimension.com/")
        # --- domani c'è…
        tom = [e for e in clubs if e["when"] == (day + timedelta(days=1)).isoformat()]
        if tom:
            names = " e ".join(e["name"] for e in tom)
            add(f"rp-{md}-eve", f"{ds} 16:00", f"🔁 Domani c'è {names}: ricondividi il post nelle storie\n"
                "1) Apri il nostro post → Condividi → \"Aggiungi alla storia\"\n"
                f"2) Sticker LINK: {tom[0]['link']}\n3) Testo \"DOMANI 🔥\" + countdown\n🎵 Aggiungi la MUSICA\n"
                "https://www.instagram.com/eventdimension_experience/")
    if not new:
        print("Piano già completo per i prossimi", DAYS, "giorni.")
        return 0
    cal += new
    cal.sort(key=lambda r: r["datetime"])
    with open(os.path.join(HERE, "calendar.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(cal)
    print(f"Aggiunti {len(new)} promemoria fino al {(today + timedelta(days=DAYS)).isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
