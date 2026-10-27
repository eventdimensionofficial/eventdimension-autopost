"""Verifica token e account senza pubblicare nulla."""
import json, os, urllib.parse, urllib.request
tok = os.environ.get("IG_TOKEN", ""); uid = os.environ.get("IG_USER_ID", "")
base = os.environ.get("MEDIA_BASE", "").rstrip("/")
def get(url):
    with urllib.request.urlopen(url, timeout=30) as r: return r.status, r.headers.get("Content-Type"), r.read()
ok = True
_print = print
def print(*a):
    _print(*a); _print("::notice::" + " ".join(str(x) for x in a))
try:
    q = urllib.parse.urlencode({"fields": "user_id,username,account_type", "access_token": tok})
    _, _, b = get("https://graph.instagram.com/v26.0/me?" + q)
    me = json.loads(b); print("Account:", me.get("username"), "| tipo:", me.get("account_type"), "| user_id:", me.get("user_id"))
    if uid and str(me.get("user_id")) != uid and str(me.get("id")) != uid:
        print("ATTENZIONE: IG_USER_ID non corrisponde. Usa:", me.get("user_id")); ok = False
except urllib.error.HTTPError as e:
    print("Token NON valido:", e.read().decode(errors="replace")); ok = False
try:
    s, ct, _ = get(base + "/storia-caposile.jpg"); print("Immagini online:", s, ct)
except Exception as e:
    print("Immagini NON raggiungibili:", e); ok = False
try:
    s2, ct2, _ = get("https://raw.githubusercontent.com/" + os.environ.get("GITHUB_REPOSITORY", "") + "/main/media/post-caposile.jpg")
    print("Immagini raw:", s2, ct2)
    if "image/jpeg" not in (ct2 or ""): ok = False
except Exception as e:
    print("Immagini raw NON raggiungibili:", e); ok = False
try:
    s3, ct3, b3 = get(base + "/reel-caposile.mp4"); print("Video reel online:", s3, ct3, len(b3) // 1024, "KB")
    if "video/mp4" not in (ct3 or ""): ok = False
except Exception as e:
    print("Video reel NON raggiungibile:", e); ok = False
# notifica di prova
topic = os.environ.get("NTFY_TOPIC", "").strip()
if topic and os.environ.get("SEND_TEST") == "1":
    try:
        body = json.dumps({"topic": topic, "title": "✅ Notifiche Event Dimension attive",
                           "message": "Da ora ricevi qui i promemoria per storie e reel.",
                           "tags": ["tada"]}).encode()
        req = urllib.request.Request("https://ntfy.sh", data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30); print("Notifica di prova inviata")
    except Exception as e:
        print("Notifica NON inviata:", e); ok = False
elif not topic:
    print("NTFY_TOPIC non impostato")
print("TUTTO OK" if ok else "CI SONO PROBLEMI"); raise SystemExit(0 if ok else 1)
