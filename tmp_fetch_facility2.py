import re
import urllib.request
from pathlib import Path

out = Path(r"C:\Users\hp\Documents\PROJECTS\Queue_System\frontend\public")
headers = {"User-Agent": "Mozilla/5.0"}

urls = [
    # Kabale news / gallery common campus imagery
    "https://news.kab.ac.ug/wp-content/uploads/2024/08/Kabale-University-Main-Campus.jpg",
    "https://news.kab.ac.ug/wp-content/uploads/2025/01/Kabale-University.jpg",
    "https://www.kab.ac.ug/wp-content/uploads/2024/01/Kabale-University-Campus.jpg",
    "https://www.kab.ac.ug/wp-content/uploads/2023/08/Teaching-Facility.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Kabale_University.jpg/1280px-Kabale_University.jpg",
    "https://upload.wikimedia.org/wikipedia/commons/8/8e/Kabale_University_logo.png",
]

# scrape a few news posts for images
seed_pages = [
    "https://news.kab.ac.ug/kabale-university-strengthens-financial-management-through-capacity-building-training-on-budget-preparation-and-accountability/",
    "https://news.kab.ac.ug/senior-staff-attend-a-workshop-on-mentorship-at-jinja-civil-service-college/",
    "https://gallery.kab.ac.ug/kabale-university-strengthens-staff-capacity-in-budget-preparation-execution-reporting-and-accountability/",
    "https://www.kab.ac.ug/about-kab/",
]

found = list(urls)
for page in seed_pages:
    try:
        req = urllib.request.Request(page, headers=headers)
        html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "ignore")
        imgs = re.findall(r"https?://[^\"' >]+\.(?:jpg|jpeg|png|webp)", html, flags=re.I)
        found.extend(imgs)
        print("page", page, "->", len(imgs))
    except Exception as e:
        print("page fail", page, e)

# also get og:image
for page in seed_pages:
    try:
        req = urllib.request.Request(page, headers=headers)
        html = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "ignore")
        for m in re.findall(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            html,
            flags=re.I,
        ):
            found.append(m)
        for m in re.findall(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            html,
            flags=re.I,
        ):
            found.append(m)
    except Exception:
        pass

seen = []
for u in found:
    if u not in seen:
        seen.append(u)

print("TOTAL", len(seen))
for u in seen[:50]:
    print(u)

best = None
for u in seen:
    try:
        req = urllib.request.Request(u, headers=headers)
        with urllib.request.urlopen(req, timeout=40) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "")
        # need a real photo, not tiny logo
        if len(data) < 80000:
            print("skip", len(data), u[:90])
            continue
        if "svg" in ctype:
            continue
        ext = ".jpg"
        low = u.lower()
        if low.endswith(".png") or "png" in ctype:
            ext = ".png"
        elif low.endswith(".webp") or "webp" in ctype:
            ext = ".webp"
        dest = out / f"kabale-teaching-facility{ext}"
        dest.write_bytes(data)
        # remove wrong jpg if we saved png
        print("SAVED", dest.name, len(data), u)
        best = dest
        # keep searching for better (larger) campus shots
        if len(data) > 200000 and any(
            k in u.lower() for k in ("campus", "teach", "facility", "build", "block")
        ):
            break
    except Exception as e:
        print("fail", u[:90], e)

print("BEST", best)
