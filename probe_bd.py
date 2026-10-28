"""Prova: legge i post recenti di altri profili (business discovery)."""
import json, os, urllib.parse, urllib.request
tok = os.environ["IG_TOKEN"]; uid = os.environ["IG_USER_ID"]
C = """monsterlandfestival monsterland_festival monsterlandhalloween monsterland.festival monsterland_halloween_festival
amnesiamilano amnesia_milano ilmuretto ilmurettojesolo muretto_jesolo ilmuretto_jesolo caposilefestival caposile_festival caposile
fabriquemilano fabrique_milano visionmilano vision_milano terminal1cinecitta neon_roma
timewarp_official timewarp timewarpfestival time_warp_official sunwavesfestival sunwaves_festival sunwaves
musiconfestival musicon_festival musiconibiza musicon zrcespringbreak zrce_spring_break terminalv terminalvfestival terminal_v_festival
awakeningsfestival awakenings monegrosfestival monegrosdesertfestival monegros_festival barrakudfestival barrakud barrakud_festival
streetparadezurich streetparade street_parade_zurich jambackmusic jamback frankyrizardo marcocarola holypriest holypriestmusic traumer traumer_music""".split()
ok = []
for u in C:
    q = urllib.parse.urlencode({"fields": f"business_discovery.username({u}){{username,followers_count,media_count,media.limit(2){{timestamp,media_type,media_product_type,permalink}}}}", "access_token": tok})
    try:
        with urllib.request.urlopen(f"https://graph.instagram.com/v26.0/{uid}?" + q, timeout=30) as r:
            d = json.loads(r.read())["business_discovery"]
            m = d.get("media", {}).get("data", [])
            msg = f"OK {u} followers={d.get('followers_count')} ultimo={m[0]['timestamp'] if m else '-'} {m[0].get('media_product_type') if m else ''}"
            ok.append(u)
    except urllib.error.HTTPError as e:
        msg = f"NO {u}: {e.read().decode(errors='replace')[:160]}"
    print(msg); print("::notice::" + msg)
print("::notice::TROVATI: " + " ".join(ok))
