"""Load the simulated groups and seed_posts.json into a fresh index.

Every post goes through the real pipeline (Muse Spark, SAM 3.1, DINOv3), so
this spends Meta Model API credit: roughly one Muse Spark call per post and
one SAM call per photo.

Run from the project folder: python -m demo_data.seed
"""
import json
import sys
from pathlib import Path

from app import ingest, store

HERE = Path(__file__).parent
TODAY = "2026-10-20"


def main():
    posts = json.loads((HERE / "seed_posts.json").read_text(encoding="utf-8"))
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(posts)
    store.reset()
    for g in json.loads((HERE / "groups.json").read_text(encoding="utf-8")):
        store.upsert_group(g)
    for n, p in enumerate(posts[:limit], 1):
        images = [(HERE / f).read_bytes() for f in p["photos"]]
        post_id = ingest.ingest_post(
            p["text"], images, p["poster"], post_type=p["post_type"],
            group_id=p["group_id"], contact_messenger=p.get("contact_messenger", ""),
            contact_phone=p.get("contact_phone", ""), contact_email=p.get("contact_email", ""),
            created_at=p["created_at"], today=TODAY, demo_pet=p["demo_pet"],
            credits=p["credits"], notify=False)
        print(f"[{n}/{limit}] post {post_id}: {p['post_type']} {p['demo_pet']}", flush=True)


if __name__ == "__main__":
    main()
