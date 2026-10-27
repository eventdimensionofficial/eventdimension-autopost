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


def media_url(name):
    """URL pubblico dell'immagine. Le immagini esterne non JPG (webp, png)
    vengono convertite al volo in JPG tramite images.weserv.nl."""
    name = name.strip()
    if name.startswith("http://") or name.startswith("https://"):
        if is_jpg(name):
            return name
        bare = name.split("://", 1)[1]
        return "https://images.weserv.nl/?" + urllib.parse.urlencode({"url": bare, "output": "jpg", "q": "90"})
    if not is_jpg(name):
        raise RuntimeError(f"{name}: i file in media/ devono essere JPG")
    return f"{MEDIA_BASE}/{urllib.parse.quote(name)}"


def notify(row):
    """Promemoria sul telefono (app ntfy) per storie/reel da pubblicare a mano."""
    if not NTFY_TOPIC:
        raise RuntimeError("NTFY_TOPIC non impostato")
    text = (row.get("caption") or "").strip()
    lines = text.splitlines() or ["Contenuto da pubblicare"]
    msg = {"topic": NTFY_TOPIC, "title": lines[0][:120],
           "message": "\n".join(lines[1:]).strip() or lines[0],
           "tags": ["iphone"], "priority": 4, "actions": []}
    links = re.findall(r"https?://\S+", text)
    files = [m for m in (row.get("media") or "").split("|") if m.strip()]
    if links:
        msg["click"] = links[0]
        msg["actions"].append({"action": "view", "label": "Biglietti", "url": links[0]})
    if files:
        img = media_url(files[0])
        msg["attach"] = img
        msg["actions"].append({"action": "view", "label": "Immagine", "url": img})
    if DRY:
        log("  [dry-run] notifica", json.dumps(msg, ensure_ascii=False))
        return "dry-notify"
    req = urllib.request.Request(NTFY_SERVER, data=json.dumps(msg).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode()).get("id", "sent")


def wait_ready(container_id, tries=10, pause=6):
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

    if kind == "STORY":
        cid = container({"image_url": media_url(files[0]), "media_type": "STORIES"})
    elif kind == "POST" and len(files) == 1:
        cid = container({"image_url": media_url(files[0]), "caption": caption})
    elif kind in ("POST", "CAROUSEL"):
        if len(files) < 2:
            raise RuntimeError("un carousel serve almeno 2 immagini")
        children = [container({"image_url": media_url(f), "is_carousel_item": "true"}) for f in files[:20]]
        cid = container({"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption})
    else:
        raise RuntimeError(f"tipo sconosciuto: {kind}")
    return publish(cid)


def main():
    with open(CAL, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    now = datetime.now(TZ)
    changed = False
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
            continue
        if now - when > MAX_LATE:
            row["status"], row["note"] = "skipped", f"troppo in ritardo ({now:%d/%m %H:%M})"
            changed = True
            log("SALTATO", row["id"], row["type"], row["datetime"])
            continue
        log("PUBBLICO", row["id"], row["type"], row["datetime"], row["media"])
        try:
            mid = do_row(row)
            row["status"], row["result"], row["note"] = "published", mid, f"ok {datetime.now(TZ):%d/%m %H:%M}"
            log("  OK", mid)
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
