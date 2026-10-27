"""
Event Dimension – genera automaticamente le grafiche degli eventi.

Legge events.csv (slug,name,sub,date,venue,link[,image]) e, per ogni evento
che non ha ancora i file in media/, scarica la locandina dalla pagina evento
del sito (og:image) e crea:
  media/post-<slug>.jpg        locandina per post (JPG, max 1080 px)
  media/storia-<slug>-link.jpg storia verticale 1080x1920 con spazio per lo sticker link
  media/storia-<slug>.jpg      storia verticale con "link in bio"
  media/reel-<slug>.mp4        reel 10 secondi 1080x1920

Uso: python generate.py [--force slug ...] [--no-reel]
"""
import csv, html, io, os, re, shutil, subprocess, sys, urllib.parse, urllib.request
from PIL import Image, ImageEnhance, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
MEDIA = os.path.join(HERE, "media")
SRC = os.path.join(MEDIA, "src")
FONTS = os.path.join(HERE, "assets", "fonts")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
FPS, DUR = 30, 10.0


def log(*a):
    print(*a, flush=True)


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
        return r.headers.get("Content-Type") or "", r.read()


def find_poster(page_url):
    """Trova l'immagine principale della pagina evento (og:image o prima immagine in wp-content/uploads)."""
    _, b = get(page_url)
    h = b.decode("utf-8", "replace")
    for pat in (r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
                r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)'):
        m = re.search(pat, h, re.I)
        if m:
            return html.unescape(m.group(1))
    m = re.search(r'(https?://[^"\'\s]+/wp-content/uploads/[^"\'\s]+\.(?:jpe?g|png|webp))', h, re.I)
    if m:
        return m.group(1)
    raise RuntimeError("nessuna immagine trovata nella pagina")


def image_candidates(ev):
    """URL da provare per la locandina: colonna image (con varianti WordPress) e og:image della pagina."""
    out = []
    img = (ev.get("image") or "").strip()
    if img:
        base, ext = img.rsplit(".", 1)
        clean = re.sub(r"-optimized$", "", base)
        for b in (base, clean):
            for e in (ext, "jpg", "png", "webp"):
                if f"{b}.{e}" not in out:
                    out.append(f"{b}.{e}")
    try:
        out.append(find_poster(ev["link"]))
    except Exception:
        pass
    return out


def font_css():
    faces = []
    for fam, key, ws in (("Space Grotesk", "space-grotesk", (500, 600, 700)), ("Inter", "inter", (400, 500, 600))):
        for w in ws:
            faces.append(f"@font-face{{font-family:'{fam}';font-weight:{w};src:url(file://{FONTS}/{key}-latin-{w}-normal.woff2)}}")
    return "".join(faces)


BASE_CSS = """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1920px;overflow:hidden;background:#000;font-family:Inter,sans-serif;color:#fff}
.bg{position:absolute;inset:-120px;background-size:cover;background-position:center}
.shade{position:absolute;inset:0;background:linear-gradient(180deg,rgba(0,0,0,.6),rgba(0,0,0,0) 25%,rgba(0,0,0,0) 55%,rgba(0,0,0,.8))}
.brand{position:absolute;left:0;right:0;top:250px;text-align:center}
.brand span{display:inline-block;font:600 26px/1 Inter;letter-spacing:.32em;text-transform:uppercase;padding:14px 26px;border-radius:999px;background:rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.25)}
.wrap{position:absolute;left:80px;top:340px;width:920px;height:920px;border-radius:28px;overflow:hidden;box-shadow:0 50px 120px rgba(0,0,0,.75)}
.poster{position:absolute;inset:0;background-size:contain;background-repeat:no-repeat;background-position:center}
.info{position:absolute;left:0;right:0;top:1300px;text-align:center;padding:0 60px}
.sub{font:600 28px/1 Inter;letter-spacing:.24em;text-transform:uppercase;color:rgba(255,255,255,.75)}
.d{margin-top:20px;font:700 100px/1 'Space Grotesk';letter-spacing:-.035em}
.d.long{font-size:78px}
.v{margin-top:18px;font:500 40px/1.2 'Space Grotesk';color:rgba(255,255,255,.88)}
.cta{position:absolute;left:0;right:0;top:1520px;text-align:center}
.cta span{display:inline-block;font:700 40px/1 'Space Grotesk';padding:24px 40px;border-radius:999px;background:#fff;color:#0a0a0a}
.cta small{display:block;margin-top:16px;font:600 28px/1 Inter;color:rgba(255,255,255,.8)}
.intro{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:0 60px;opacity:0}
.intro .d{font-size:140px}.intro .d.long{font-size:100px}
.flash{position:absolute;inset:0;background:#fff;opacity:0}
"""

REEL_JS = """
const $=id=>document.getElementById(id);
const cl=(v,a=0,b=1)=>Math.min(b,Math.max(a,v)), p=(t,a,b)=>cl((t-a)/(b-a));
const eo=v=>1-Math.pow(1-v,3), eb=v=>{const c1=1.70158,c3=c1+1;return 1+c3*Math.pow(v-1,3)+c1*Math.pow(v-1,2)};
window.render=function(t){
  $('intro').style.opacity=t<1.6?1:1-p(t,1.6,1.9);
  const k=eb(p(t,.1,.5)); $('id').style.transform=`scale(${1.6-.6*k})`; $('id').style.opacity=p(t,.1,.2); $('ik').style.opacity=p(t,.45,.7);
  const w=eo(p(t,1.7,2.4)); $('wrap').style.opacity=p(t,1.7,1.9); $('wrap').style.transform=`translateY(${(1-w)*260}px) scale(${.85+.15*w})`;
  $('poster').style.transform=`scale(${1+.08*p(t,1.7,10)})`;
  $('brand').style.opacity=p(t,2,2.4);
  const i=eo(p(t,2.6,3.1)); $('info').style.opacity=i; $('info').style.transform=`translateY(${(1-i)*50}px)`;
  const c=eb(p(t,6.2,6.7)); $('cta').style.opacity=p(t,6.2,6.35); $('cta').style.transform=`scale(${.6+.4*c})`;
  $('fx').style.opacity=t>1.65&&t<1.85?(1-Math.abs(t-1.75)/.1)*.5:0;
  $('bg').style.transform=`scale(${1.1+.08*Math.sin(t*.6)})`;
};
"""


def page_html(ev, poster, bg, cta, reel=False):
    long = " long" if len(ev["date"]) > 12 else ""
    sub = html.escape(ev.get("sub") or "")
    date, venue = html.escape(ev["date"]), html.escape(ev["venue"])
    intro = (f'<div class="intro" id="intro"><div class="d{long}" id="id">{date}</div>'
             f'<div class="sub" id="ik" style="margin-top:30px">{venue}</div></div>') if reel else ""
    style = "" if reel else ' style="opacity:1"'
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{font_css()}{BASE_CSS}</style></head><body>
<div class="bg" id="bg" style="background-image:url('file://{bg}')"></div><div class="shade"></div>{intro}
<div class="brand" id="brand"><span>Event Dimension</span></div>
<div class="wrap" id="wrap"><div class="poster" id="poster" style="background-image:url('file://{poster}')"></div></div>
<div class="info" id="info"><div class="sub">{sub}</div><div class="d{long}">{date}</div><div class="v">{venue}</div></div>
<div class="cta" id="cta">{cta}</div><div class="flash" id="fx"></div>
{"<script>" + REEL_JS + "render(0);</script>" if reel else ""}</body></html>"""


def build(ev, force=False, reel=True, page=None):
    slug = ev["slug"]
    outs = {k: os.path.join(MEDIA, v.format(slug)) for k, v in
            (("post", "post-{}.jpg"), ("story", "storia-{}.jpg"), ("link", "storia-{}-link.jpg"), ("reel", "reel-{}.mp4"))}
    need = [k for k, p in outs.items() if force or not os.path.exists(p)]
    if not reel and "reel" in need:
        need.remove("reel")
    if not need:
        return False
    os.makedirs(SRC, exist_ok=True)
    src = os.path.join(SRC, f"{slug}.jpg")
    if force or not os.path.exists(src):
        data = None
        for img_url in image_candidates(ev):
            try:
                ct, d = get(img_url)
                if ct.startswith("image/"):
                    data = d; log(f"[{slug}] locandina: {img_url}"); break
            except Exception:
                pass
        if data is None:
            raise RuntimeError("locandina non trovata (controlla la colonna image o il link)")
        Image.open(io.BytesIO(data)).convert("RGB").save(src, "JPEG", quality=95)
    im = Image.open(src).convert("RGB")
    # post: JPG max 1080 px, rapporto consentito da Instagram (4:5 … 1.91:1)
    if "post" in need:
        p = im.copy(); p.thumbnail((1080, 1350)); p.save(outs["post"], "JPEG", quality=90)
    bg = os.path.join(SRC, f"{slug}-bg.jpg")
    b = im.copy().resize((540, 960)).filter(ImageFilter.GaussianBlur(40))
    b = ImageEnhance.Brightness(ImageEnhance.Color(b).enhance(1.5)).enhance(0.5); b.save(bg, quality=85)
    ctas = {"story": '<span>🎟️ Biglietti · link in bio</span><small>eventdimension.com</small>',
            "link": '<span>🎟️ Biglietti qui sotto 👇</span>',
            "reel": '<span>🎟️ Biglietti · link in bio</span><small>eventdimension.com</small>'}
    tmp = os.path.join(HERE, ".tmp-gen"); os.makedirs(tmp, exist_ok=True)
    for k in ("story", "link"):
        if k in need:
            f = os.path.join(tmp, f"{slug}-{k}.html"); open(f, "w").write(page_html(ev, src, bg, ctas[k]))
            page.goto("file://" + f); page.wait_for_timeout(300)
            page.screenshot(path=outs[k], type="jpeg", quality=88)
    if "reel" in need:
        frames = os.path.join(tmp, "frames"); shutil.rmtree(frames, ignore_errors=True); os.makedirs(frames)
        f = os.path.join(tmp, f"{slug}-reel.html"); open(f, "w").write(page_html(ev, src, bg, ctas["reel"], reel=True))
        page.goto("file://" + f); page.wait_for_timeout(400)
        for i in range(int(DUR * FPS)):
            page.evaluate(f"render({i / FPS})")
            page.screenshot(path=os.path.join(frames, f"f{i:04d}.jpg"), type="jpeg", quality=90)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(frames, "f%04d.jpg"),
                        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000", "-shortest",
                        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "22", "-r", "30",
                        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", outs["reel"]], check=True)
    log(f"[{slug}] creati: {', '.join(need)}")
    return True


def main():
    args = sys.argv[1:]
    force = set(args[args.index("--force") + 1:]) if "--force" in args else set()
    reel = "--no-reel" not in args
    path = os.path.join(HERE, "events.csv")
    if not os.path.exists(path):
        log("events.csv non trovato"); return 0
    events = [e for e in csv.DictReader(open(path, encoding="utf-8")) if e.get("slug")]
    from playwright.sync_api import sync_playwright
    made, errors = 0, 0
    with sync_playwright() as pw:
        br = pw.chromium.launch(); page = br.new_page(viewport={"width": 1080, "height": 1920})
        for ev in events:
            try:
                if build(ev, force=ev["slug"] in force, reel=reel, page=page):
                    made += 1
            except Exception as e:
                errors += 1
                log(f"::warning::[{ev['slug']}] grafiche non create: {e}")
        br.close()
    shutil.rmtree(os.path.join(HERE, ".tmp-gen"), ignore_errors=True)
    log(f"Eventi aggiornati: {made}, errori: {errors}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
