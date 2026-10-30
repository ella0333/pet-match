import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("PET_MATCH_DATA", ROOT / "data"))
UPLOADS = DATA / "uploads"
DB_PATH = DATA / "pet_match.db"
SNAPSHOT_PATH = DATA / "seed_snapshot.db"
USAGE_PATH = DATA / "usage.jsonl"
TOWN_PATH = ROOT / "demo_data" / "town.json"

META_BASE_URL = "https://api.meta.ai/v1"
CHAT_MODEL = "muse-spark-1.3"
SAM_MODEL = "sam-3.1"
EMBED_APP = "pet-match-embed"

# Prices in dollars, from the Meta Model API pricing page.
PRICE_INPUT_PER_TOKEN = 1.25 / 1_000_000
PRICE_OUTPUT_PER_TOKEN = 4.25 / 1_000_000
PRICE_SAM_PER_IMAGE = 2.50 / 1000

# Limits for the public demo. Only new posts and new match checks cost money.
HOSTED = os.environ.get("PET_MATCH_HOSTED") == "1"
POSTS_PER_VISITOR_PER_DAY = 3
POSTS_PER_DAY = 60
NEW_SEARCHES_PER_VISITOR_PER_DAY = 10
NEW_SEARCHES_PER_DAY = 200
SPEND_CEILING_USD = float(os.environ.get("PET_MATCH_SPEND_CEILING", "25"))
MAX_PHOTOS = 4
MAX_PHOTO_BYTES = 10 * 1024 * 1024


def meta_api_key() -> str:
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        raise RuntimeError("Set MODEL_API_KEY to your Meta Model API key.")
    return key


DATA.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(exist_ok=True)
