"""Prova: elenca le immagini dalla API WordPress e scarica le più recenti."""
import urllib.request, io, json
from PIL import Image
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as r:
        return r.status, r.headers.get("Content-Type"), r.read()
_, _, b = get("https://eventdimension.com/wp-json/wp/v2/media?per_page=15&media_type=image&_fields=id,date,source_url,title")
items = json.loads(b)
ok = 0
for it in items:
    u = it["source_url"]
    try:
        s, ct, data = get(u)
        sz = Image.open(io.BytesIO(data)).size if (ct or "").startswith("image/") else "-"
        if sz != "-": ok += 1
        print(f"::notice::{it['date'][:10]} {s} {ct} {sz} {u.rsplit('/',1)[1][:70]}")
    except Exception as e:
        print(f"::notice::ERRORE {e} {u.rsplit('/',1)[1][:70]}")
print(f"::notice::Scaricate {ok}/{len(items)}")
# pagine evento: immagine in evidenza via API
_, _, b = get("https://eventdimension.com/wp-json/wp/v2/types?_fields=slug,rest_base")
print("::notice::Tipi contenuto:", ", ".join(f"{k}->{v.get('rest_base')}" for k, v in json.loads(b).items())[:900])
