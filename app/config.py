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

# The one group whose admin opt-in switch the demo shows.
OPT_IN_DEMO_GROUP = "southgate-buy-sell"

# Prices in dollars, from the Meta Model API pricing page.
PRICE_INPUT_PER_TOKEN = 1.25 / 1_000_000
PRICE_OUTPUT_PER_TOKEN = 4.25 / 1_000_000
PRICE_SAM_PER_IMAGE = 2.50 / 1000

# Limits for the public demo. Only searches with an uploaded photo cost money.
HOSTED = os.environ.get("PET_MATCH_HOSTED") == "1"
SEARCHES_PER_VISITOR_PER_DAY = 5
SEARCHES_PER_DAY = 80
# Searching stops before the free Meta credit runs out. The token log
# undercounts what Meta bills by roughly 15 to 20 percent, so estimates are
# padded, and a small buffer is kept on top.
CREDIT_LEFT_USD = float(os.environ.get("PET_MATCH_CREDIT_LEFT", "147.55"))
SPEND_SAFETY_FACTOR = 1.3
CREDIT_BUFFER_USD = 5.0
MAX_PHOTOS = 4
MAX_PHOTO_BYTES = 10 * 1024 * 1024


def meta_api_key() -> str:
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        raise RuntimeError("Set MODEL_API_KEY to your Meta Model API key.")
    return key


DATA.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(exist_ok=True)
