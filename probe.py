"""Prova diverse vie per scaricare una locandina dal sito (solo test)."""
import urllib.request, io
from PIL import Image
SRC = "eventdimension.com/wp-content/uploads/2026/08/Monegros-2027-1024x1024-1-optimized.webp"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Accept": "image/*"}
tries = {
  "diretto": "https://" + SRC,
  "wp-photon i0": "https://i0.wp.com/" + SRC,
  "wp-photon i2 jpg": "https://i2.wp.com/" + SRC + "?w=1080",
  "facebook UA": ("https://" + SRC, {"User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"}),
  "google UA": ("https://" + SRC, {"User-Agent": "Mozilla/5.0 (compatible; Googlebot-Image/1.0)"}),
  "wordpress API": "https://eventdimension.com/wp-json/wp/v2/media?per_page=1",
}
for name, t in tries.items():
    url, h = (t if isinstance(t, tuple) else (t, UA))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=30) as r:
            b = r.read(); ct = r.headers.get("Content-Type")
            info = ""
            if (ct or "").startswith("image/"):
                info = str(Image.open(io.BytesIO(b)).size)
            print(f"::notice::{name}: {r.status} {ct} {len(b)}B {info}")
    except Exception as e:
        print(f"::notice::{name}: ERRORE {e}")
