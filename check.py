"""Verifica token e account senza pubblicare nulla."""
import json, os, urllib.parse, urllib.request
tok = os.environ.get("IG_TOKEN", ""); uid = os.environ.get("IG_USER_ID", "")
base = os.environ.get("MEDIA_BASE", "").rstrip("/")
def get(url):
    with urllib.request.urlopen(url, timeout=30) as r: return r.status, r.headers.get("Content-Type"), r.read()
ok = True
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
print("TUTTO OK" if ok else "CI SONO PROBLEMI"); raise SystemExit(0 if ok else 1)
