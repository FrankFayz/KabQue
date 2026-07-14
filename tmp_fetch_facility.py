import re
import urllib.request
from pathlib import Path

out = Path(r"C:\Users\hp\Documents\PROJECTS\Queue_System\frontend\public")
headers = {"User-Agent": "Mozilla/5.0"}

pages = [
    "https://www.kab.ac.ug/",
    "https://news.kab.ac.ug/",
    "https://www.kab.ac.ug/about-kab/",
]

cands = []
for u in pages:
    try:
        req = urllib.request.Request(u, headers=headers)
        html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "ignore")
        found = re.findall(r"https?://[^\"' ]+\.(?:jpg|jpeg|png|webp)", html, flags=re.I)
        for m in found:
            low = m.lower()
            if any(
                k in low
                for k in (
                    "teach",
                    "campus",
                    "build",
                    "facility",
                    "lecture",
                    "block",
                    "library",
                    "class",
                    "infrastructure",
                    "faculty",
                    "kikungiri",
                )
            ):
                cands.append(m)
        print("OK", u, "imgs", len(found))
    except Exception as e:
        print("FAIL", u, e)

# known gallery / news style fallbacks
extra = [
    "https://www.kab.ac.ug/wp-content/uploads/2022/08/Kabale-University-Website-Logo-2.jpg",
]
cands = list(dict.fromkeys(cands + extra))
print("CANDS", len(cands))
for c in cands[:30]:
    print(c)

# Prefer larger campus-looking photos
preferred_keywords = ("teach", "facility", "campus", "block", "library", "build")
ranked = sorted(
    cands,
    key=lambda u: (
        0 if any(k in u.lower() for k in preferred_keywords) else 1,
        len(u),
    ),
)

saved = None
for u in ranked:
    try:
        req = urllib.request.Request(u, headers=headers)
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "")
        if len(data) < 20000:
            print("skip small", u, len(data))
            continue
        if "image" not in ctype and not u.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            print("skip nonimage", u, ctype)
            continue
        dest = out / "kabale-teaching-facility.jpg"
        if u.lower().endswith(".png"):
            dest = out / "kabale-teaching-facility.png"
        elif u.lower().endswith(".webp"):
            dest = out / "kabale-teaching-facility.webp"
        dest.write_bytes(data)
        print("SAVED", dest, len(data), "from", u)
        saved = dest
        break
    except Exception as e:
        print("download fail", u, e)

if not saved:
    # scrape gallery home for any large jpg
    try:
        req = urllib.request.Request("https://gallery.kab.ac.ug/", headers=headers)
        html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "ignore")
        for u in re.findall(r"https?://[^\"' ]+\.(?:jpg|jpeg)", html, flags=re.I):
            try:
                req = urllib.request.Request(u, headers=headers)
                data = urllib.request.urlopen(req, timeout=40).read()
                if len(data) > 40000:
                    dest = out / "kabale-teaching-facility.jpg"
                    dest.write_bytes(data)
                    print("SAVED gallery", dest, len(data), "from", u)
                    saved = dest
                    break
            except Exception as e:
                print("g fail", e)
    except Exception as e:
        print("gallery fail", e)

print("DONE", saved)
