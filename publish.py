"""
Event Dimension – pubblicazione automatica su Instagram.

Legge calendar.csv e pubblica i contenuti arrivati all'orario previsto
usando l'API di Instagram (Instagram Login, graph.instagram.com).

Variabili d'ambiente (GitHub Secrets):
  IG_TOKEN    token di accesso Instagram (long-lived)
  IG_USER_ID  ID dell'account Instagram professionale
  MEDIA_BASE  URL pubblico della cartella media (GitHub Pages),
              es. https://utente.github.io/eventdimension-autopost/media
Opzionali:
  DRY_RUN=1   non chiama Instagram, simula soltanto
  MAX_LATE_HOURS (default 6): oltre questo ritardo un contenuto viene
              segnato "skipped" invece di essere pubblicato in ritardo.
"""
import csv, json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Rome")
API = os.environ.get("IG_API_BASE", "https://graph.instagram.com/v26.0")
HERE = os.path.dirname(os.path.abspath(__file__))
CAL = os.path.join(HERE, "calendar.csv")
FIELDS = ["id", "datetime", "type", "media", "caption", "status", "result", "note"]

TOKEN = os.environ.get("IG_TOKEN", "")
IG_ID = os.environ.get("IG_USER_ID", "")
MEDIA_BASE = os.environ.get("MEDIA_BASE", "").rstrip("/")
DRY = os.environ.get("DRY_RUN") == "1"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
MAX_LATE = timedelta(hours=float(os.environ.get("MAX_LATE_HOURS", "6")))


def log(*a):
    print(datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def api(method, path, params=None):
    params = dict(params or {})
    params["access_token"] = TOKEN
    url = f"{API}/{path}"
    data = None
    if method == "GET":
        url += "?" + urllib.parse.urlencode(params)
    else:
        data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            msg = json.loads(body).get("error", {}).get("message", body)
        except Exception:
            msg = body
        raise RuntimeError(f"HTTP {e.code}: {msg}") from None


def is_jpg(u):
    return u.lower().split("?")[0].endswith((".jpg", ".jpeg"))


def is_video(u):
    return u.lower().split("?")[0].endswith((".mp4", ".mov"))


def media_url(name):
    """URL pubblico dell'immagine. Le immagini esterne non JPG (webp, png)
    vengono convertite al volo in JPG tramite images.weserv.nl."""
    name = name.strip()
    if name.startswith("http://") or name.startswith("https://"):
        if is_jpg(name):
            return name
        raise RuntimeError(f"{name}: immagine non JPG non ancora convertita")
    if not (is_jpg(name) or is_video(name)):
        raise RuntimeError(f"{name}: i file in media/ devono essere JPG (o MP4 per i reel)")
    return f"{MEDIA_BASE}/{urllib.parse.quote(name)}"


REPO = os.environ.get("GITHUB_REPOSITORY", "")


def fetch_image(url):
    """Scarica un'immagine; se il sito risponde con una pagina anti-bot usa un vero browser."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                                                   "Accept": "image/avif,image/webp,image/*,*/*"})
        with urllib.request.urlopen(req, timeout=60) as r:
            if (r.headers.get("Content-Type") or "").startswith("image/"):
                return r.read()
    except Exception as e:
        log("  download diretto fallito:", e)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        data = None
        for _ in range(3):
            resp = pg.goto(url, wait_until="networkidle", timeout=60000)
            if resp and (resp.headers.get("content-type") or "").startswith("image/"):
                data = resp.body(); break
            pg.wait_for_timeout(4000)
        b.close()
    if not data:
        raise RuntimeError("il sito non ha restituito un'immagine")
    return data


def localize(url):
    """Scarica un'immagine esterna non JPG (webp, png...), la converte in JPG
    dentro media/ext/ e restituisce l'URL raw di GitHub (disponibile subito dopo il push)."""
    import hashlib, io
    from PIL import Image
    h = hashlib.sha1(url.encode()).hexdigest()[:12]
    rel = f"media/ext/{h}.jpg"
    path = os.path.join(HERE, rel)
    if not os.path.exists(path):
        data = fetch_image(url)
        im = Image.open(io.BytesIO(data)).convert("RGB")
        if max(im.size) > 1440:
            im.thumbnail((1440, 1440))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        im.save(path, "JPEG", quality=90)
    return f"https://raw.githubusercontent.com/{REPO}/main/{rel}"


def prepare(rows):
    """Converte in anticipo le immagini esterne non JPG delle righe in programma."""
    changed, fresh = False, set()
    for row in rows:
        if row.get("status", "").strip().lower() not in ("", "scheduled"):
            continue
        if row.get("type", "").strip().upper() == "REMINDER":
            continue
        parts = [m.strip() for m in (row.get("media") or "").split("|") if m.strip()]
        new = []
        for m in parts:
            if m.startswith(("http://", "https://")) and not is_jpg(m) and not is_video(m) and "eventdimension.com" not in m:
                try:
                    m2 = localize(m)
                    log("CONVERTITA", m, "->", m2)
                    new.append(m2); fresh.add(row["id"]); changed = True
                    continue
                except Exception as e:
                    log("  conversione fallita", m, e)
            new.append(m)
        row["media"] = "|".join(new)
    return changed, fresh


def candidates(url):
    """Per immagini esterne non JPG (es. -optimized.webp di WordPress) prova le versioni JPG originali."""
    u = url.strip()
    if is_jpg(u):
        return [u]
    base = u.split("?")[0].rsplit(".", 1)[0]
    out = []
    for b in (base, re.sub(r"-optimized$", "", base), re.sub(r"-\d+x\d+(-\d+)?(-optimized)?$", "", base)):
        for ext in (".jpg", ".jpeg"):
            if b + ext not in out:
                out.append(b + ext)
    return out


def img_container(f, extra):
    """Crea il container per un'immagine provando, se serve, le versioni JPG alternative."""
    f = f.strip()
    if not f.startswith(("http://", "https://")):
        return container({**extra, "image_url": media_url(f)})
    last = None
    for u in candidates(f):
        try:
            cid = container({**extra, "image_url": u})
            if u != f:
                log("  usata versione JPG:", u)
            return cid
        except Exception as e:
            last = e
    raise RuntimeError(f"nessuna versione JPG leggibile per {f}: {last}")


def notify(row, at=None):
    """Promemoria sul telefono (app ntfy) per storie/reel da pubblicare a mano.
    Con `at` il messaggio viene consegnato da ntfy esattamente a quell'ora (max 3 giorni)."""
    if not NTFY_TOPIC:
        raise RuntimeError("NTFY_TOPIC non impostato")
    text = (row.get("caption") or "").strip()
    rid = (row.get("id") or "").lower()
    if rid.startswith(("s-", "rp-")) and not re.search(r"musica|audio", text, re.I):
        text += "\n🎵 Aggiungi la MUSICA: sticker Musica → un brano di tendenza (techno/house), parte più carica"
    lines = text.splitlines() or ["Contenuto da pubblicare"]
    msg = {"topic": NTFY_TOPIC, "title": lines[0][:120],
           "message": "\n".join(lines[1:]).strip() or lines[0],
           "tags": ["iphone"], "priority": 4, "actions": []}
    links = re.findall(r"https?://\S+", text)
    files = [m for m in (row.get("media") or "").split("|") if m.strip()]
    if links:
        msg["click"] = links[0]
        label = ("Apri Instagram" if "instagram.com" in links[0] else
                 "Apri il sito" if links[0].rstrip("/") == "https://eventdimension.com" else "Biglietti")
        msg["actions"].append({"action": "view", "label": label, "url": links[0]})
    if files:
        f0 = files[0].strip()
        img = f0 if f0.startswith(("http://", "https://")) else media_url(f0)
        msg["attach"] = img
        msg["actions"].append({"action": "view", "label": "Video" if is_video(img) else "Immagine", "url": img})
        for i, f in enumerate(files[1:], 2):
            if len(msg["actions"]) >= 3:
                break
            u = f.strip() if f.strip().startswith(("http://", "https://")) else media_url(f.strip())
            msg["actions"].append({"action": "view", "label": f"Immagine {i}", "url": u})
    if at is not None:
        msg["delay"] = str(int(at.timestamp()))
    if DRY:
        log("  [dry-run] notifica", json.dumps(msg, ensure_ascii=False))
        return "dry-notify"
    req = urllib.request.Request(NTFY_SERVER, data=json.dumps(msg).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode()).get("id", "sent")


def wait_ready(container_id, tries=10, pause=6):
    """Attende che Instagram abbia elaborato il contenuto (i video richiedono di più)."""
    for _ in range(tries):
        st = api("GET", container_id, {"fields": "status_code"}).get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {container_id} stato {st}")
        time.sleep(pause)
    raise RuntimeError(f"container {container_id} non pronto")


def container(params):
    if DRY:
        log("  [dry-run] crea container", params)
        return "dry-container"
    cid = api("POST", f"{IG_ID}/media", params)["id"]
    if "video_url" in params:
        wait_ready(cid, tries=45, pause=10)   # fino a ~7 minuti per i video
    else:
        wait_ready(cid)
    return cid


def publish(cid):
    if DRY:
        log("  [dry-run] pubblica", cid)
        return "dry-media-id"
    return api("POST", f"{IG_ID}/media_publish", {"creation_id": cid})["id"]


def do_row(row):
    kind = row["type"].strip().upper()
    files = [m for m in row["media"].split("|") if m.strip()]
    caption = row.get("caption", "")
    if kind == "REMINDER":
        return notify(row)
    if not (TOKEN and IG_ID and MEDIA_BASE) and not DRY:
        raise RuntimeError("mancano IG_TOKEN / IG_USER_ID / MEDIA_BASE")
    if not files:
        raise RuntimeError("nessuna immagine")

    if kind == "REEL":
        if not is_video(files[0]):
            raise RuntimeError("un reel richiede un video MP4")
        params = {"media_type": "REELS", "video_url": media_url(files[0]),
                  "caption": caption, "share_to_feed": "true"}
        if len(files) > 1 and is_jpg(files[1]):
            params["cover_url"] = media_url(files[1])
        cid = container(params)
    elif kind == "STORY":
        cid = img_container(files[0], {"media_type": "STORIES"})
    elif kind == "POST" and len(files) == 1:
        cid = img_container(files[0], {"caption": caption})
    elif kind in ("POST", "CAROUSEL"):
        if len(files) < 2:
            raise RuntimeError("un carousel serve almeno 2 immagini")
        children = [img_container(f, {"is_carousel_item": "true"}) for f in files[:20]]
        cid = container({"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption})
    else:
        raise RuntimeError(f"tipo sconosciuto: {kind}")
    return publish(cid)


def repost_reminder(row, media_id, when):
    """Dopo un post/carousel pubblicato, crea un promemoria per ricondividerlo nelle storie."""
    try:
        link = api("GET", media_id, {"fields": "permalink"}).get("permalink", "")
    except Exception:
        link = ""
    title = (row.get("caption") or "").strip().splitlines()[0][:90] if row.get("caption") else row["id"]
    text = (f"🔁 Ricondividi il post nelle storie: {title}\n"
            "1) Apri il post (tocca la notifica)  2) Tasto Condividi → \"Aggiungi alla storia\"\n"
            "3) Aggiungi lo sticker LINK ai biglietti e un testo tipo \"NUOVO POST 👀\"\n" + link)
    return {"id": f"rp-{row['id']}", "datetime": when.strftime("%Y-%m-%d %H:%M"), "type": "REMINDER",
            "media": "", "caption": text, "status": "scheduled", "result": "", "note": ""}


AUTO_PUBLISH = os.environ.get("AUTO_PUBLISH", "0") == "1"   # spento: post e reel arrivano come notifica


def as_reminder(row):
    """Trasforma un post/carousel/reel/storia in un promemoria da pubblicare a mano."""
    kind = row["type"].strip().upper()
    cap = (row.get("caption") or "").strip()
    first = cap.splitlines()[0][:90] if cap else row["id"]
    n = len([m for m in row["media"].split("|") if m.strip()])
    head = {"POST": "📸 Post da pubblicare", "CAROUSEL": "📸 Carosello da pubblicare",
            "REEL": "🎬 Reel da pubblicare", "STORY": "📲 Storia da pubblicare"}.get(kind, "📸 Da pubblicare")
    if kind in ("POST", "CAROUSEL") and n > 1:
        head = "📸 Carosello da pubblicare"
    steps = (f"1) Salva {'le ' + str(n) + ' immagini (tasti Immagine)' if n > 1 else 'l' + chr(39) + 'immagine'}  2) Instagram → nuovo post\n"
             "3) Copia questa descrizione:" if kind in ("POST", "CAROUSEL") else
             "1) Salva il video  2) Instagram → nuovo Reel\n3) Aggiungi un AUDIO DI TENDENZA\n4) Descrizione:" if kind == "REEL" else
             "1) Salva l'immagine  2) Instagram → nuova storia")
    row["caption"] = f"{head}: {first}\n{steps}\n\n{cap}".strip()
    row["type"] = "REMINDER"


def main():
    with open(CAL, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    now = datetime.now(TZ)
    if not AUTO_PUBLISH:
        for r in rows:
            if r.get("status", "").strip().lower() in ("", "scheduled") and r["type"].strip().upper() != "REMINDER":
                as_reminder(r)
    changed, fresh = (False, set()) if DRY else prepare(rows)
    for row in sorted(rows, key=lambda r: r["datetime"]):
        if row.get("status", "").strip().lower() not in ("", "scheduled"):
            continue
        try:
            when = datetime.strptime(row["datetime"].strip(), "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        except ValueError:
            row["status"], row["note"] = "error", "data non valida (usa AAAA-MM-GG HH:MM)"
            changed = True
            continue
        if when > now:
            # i promemoria delle prossime 60 ore vengono affidati subito a ntfy con orario esatto
            if row["type"].strip().upper() == "REMINDER" and when - now <= timedelta(hours=60):
                try:
                    nid = notify(row, at=when)
                    row["status"], row["result"], row["note"] = "queued", nid, f"consegna programmata {when:%d/%m %H:%M}"
                    log("PROGRAMMATO", row["id"], row["datetime"])
                except Exception as e:
                    log("  ERRORE programmazione", row["id"], e)
                changed = True
            continue
        if now - when > MAX_LATE:
            row["status"], row["note"] = "skipped", f"troppo in ritardo ({now:%d/%m %H:%M})"
            changed = True
            log("SALTATO", row["id"], row["type"], row["datetime"])
            continue
        if row["id"] in fresh:
            log("RIMANDATO (immagine appena convertita)", row["id"])
            continue
        log("PUBBLICO", row["id"], row["type"], row["datetime"], row["media"])
        try:
            mid = do_row(row)
            row["status"], row["result"], row["note"] = "published", mid, f"ok {datetime.now(TZ):%d/%m %H:%M}"
            log("  OK", mid)
            kind = row["type"].strip().upper()
            if kind in ("POST", "CAROUSEL", "REEL") and not DRY and not any(x["id"] == f"rp-{row['id']}" for x in rows):
                rows.append(repost_reminder(row, mid, datetime.now(TZ) + timedelta(minutes=30)))
                log("  promemoria ricondivisione tra 30 minuti")
        except Exception as e:
            row["status"], row["note"] = "error", str(e)[:300]
            log("  ERRORE", e)
        changed = True
    if changed and not DRY:
        with open(CAL, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in FIELDS})
    if not DRY and TOKEN and IG_ID:
        try:
            lim = api("GET", f"{IG_ID}/content_publishing_limit", {"fields": "quota_usage,config"})
            log("Quota pubblicazioni 24h:", json.dumps(lim.get("data", lim)))
        except Exception as e:
            log("Quota non disponibile:", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
