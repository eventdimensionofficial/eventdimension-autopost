"""Rinnova il token Instagram (dura 60 giorni) e lo stampa per il workflow."""
import json, os, sys, urllib.parse, urllib.request

tok = os.environ.get("IG_TOKEN", "")
if not tok:
    print("IG_TOKEN mancante", file=sys.stderr); sys.exit(1)
url = "https://graph.instagram.com/refresh_access_token?" + urllib.parse.urlencode(
    {"grant_type": "ig_refresh_token", "access_token": tok})
try:
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read().decode())
except urllib.error.HTTPError as e:
    print("Rinnovo fallito:", e.read().decode(errors="replace"), file=sys.stderr); sys.exit(1)
new = data["access_token"]
days = int(data.get("expires_in", 0)) // 86400
print(f"::add-mask::{new}")
with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as f:
    f.write(f"token={new}\n")
print(f"Token rinnovato, valido ancora {days} giorni.")
