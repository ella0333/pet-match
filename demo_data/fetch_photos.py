"""Download demo pet photos from Wikimedia Commons.

Each Commons category for an individual animal becomes one pet, so several
photos of the same animal can be split into a lost post and a found post.
Only freely reusable licenses are kept, and credits.json records the author
and license of every file.
"""
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "pet-match-demo/0.1 (hackathon demo dataset)"}
OUT = Path(__file__).parent / "photos"
ROOTS = {
    "cat": ["Category:Individual cats", "Category:Cats of Wikipedians"],
    "dog": ["Category:Individual dogs", "Category:Dogs of Wikipedians",
            "Category:Dogs of Wikipedians in Baden-Württemberg",
            "Category:Dogs by named individual owners",
            "Category:German Shepherd Dog by name", "Category:Assistance dogs by name"],
}
SKIP_ROOT = ("Famous", "Fictional", "Wikipedians", "by name", "by named")
CURATION = json.loads((Path(__file__).parent / "curation.json").read_text(encoding="utf-8"))
OK_LICENSE = re.compile(r"^(CC0|Public domain|PD|CC BY(-SA)? \d)", re.I)
PHOTOS_PER_PET = 4
MIN_PHOTOS = 3
PETS_PER_SPECIES = 25


def get(url, **kw):
    for attempt in range(20):
        r = requests.get(url, headers=HEADERS, timeout=60, **kw)
        if r.status_code != 429:
            return r
        wait = min(60, int(r.headers.get("Retry-After", 0)) or 10 * (attempt + 1))
        print(f"  rate limited, waiting {wait}s", flush=True)
        time.sleep(wait)
    return r


def api(**params):
    params.update(format="json", formatversion=2)
    r = get(API, params=params)
    r.raise_for_status()
    time.sleep(1)
    return r.json()


def subcats(cat):
    data = api(action="query", list="categorymembers", cmtitle=cat,
               cmtype="subcat", cmlimit=500)
    return [m["title"] for m in data["query"]["categorymembers"]]


def single_animal_cats(root):
    out = []
    for c in subcats(root):
        if any(s in c for s in SKIP_ROOT):
            continue
        # Categories naming several animals ("X and Y") hold mixed photos.
        if re.search(r"\band\b|,", c):
            continue
        out.append(c)
    return out


def files_in(cat):
    data = api(action="query", generator="categorymembers", gcmtitle=cat,
               gcmtype="file", gcmlimit=50, prop="imageinfo",
               iiprop="url|mime|extmetadata", iiurlwidth=960)
    files = []
    for p in data.get("query", {}).get("pages", []):
        info = (p.get("imageinfo") or [{}])[0]
        if info.get("mime") not in ("image/jpeg", "image/png"):
            continue
        meta = info.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if not OK_LICENSE.match(lic):
            continue
        artist = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()
        files.append({"title": p["title"], "thumb": info.get("thumburl"),
                      "page": info.get("descriptionurl"), "license": lic,
                      "author": artist})
    return files


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    credits_path = OUT / "credits.json"
    credits = json.loads(credits_path.read_text(encoding="utf-8")) if credits_path.exists() else []
    done = {c["pet"] for c in credits}
    done |= set(CURATION["drop_pets"])
    for species, roots in ROOTS.items():
        kept = len({c["pet"] for c in credits if c["species"] == species})
        cats = [c for root in roots for c in single_animal_cats(root)]
        for cat in cats:
            if kept >= PETS_PER_SPECIES:
                break
            pet_id = f"{species}-{slug(cat.split(':', 1)[1])}"
            if pet_id in done:
                continue
            print(f"checking {cat}", flush=True)
            files = files_in(cat)
            if len(files) < MIN_PHOTOS:
                continue
            pet_dir = OUT / pet_id
            pet_dir.mkdir(exist_ok=True)
            saved = 0
            for f in files[:PHOTOS_PER_PET]:
                ext = Path(urlparse(f["thumb"]).path).suffix.lower() or ".jpg"
                dest = pet_dir / f"{saved + 1}{ext}"
                r = get(f["thumb"])
                if not r.ok:
                    continue
                dest.write_bytes(r.content)
                credits.append({"pet": pet_id, "species": species,
                                "file": dest.relative_to(OUT).as_posix(), **f})
                saved += 1
                time.sleep(3)
            if saved >= MIN_PHOTOS:
                kept += 1
                print(f"{pet_id}: {saved} photos")
            else:
                credits = [c for c in credits if c["pet"] != pet_id]
            credits_path.write_text(json.dumps(credits, indent=2), encoding="utf-8")
        print(f"{species}: {kept} pets")


if __name__ == "__main__":
    main()
