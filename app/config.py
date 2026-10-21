import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
DB_PATH = DATA / "pet_match.db"
EMB_PATH = DATA / "embeddings.npy"
TOWN_PATH = ROOT / "demo_data" / "town.json"

# The key lives outside the repo; MODEL_API_KEY overrides it when deployed.
CREDENTIALS_FILE = Path(os.environ.get("PET_MATCH_CREDENTIALS", "A:/pet credentials.txt"))

META_BASE_URL = "https://api.meta.ai/v1"
CHAT_MODEL = "muse-spark-1.3"
SAM_MODEL = "sam-3.1"
EMBED_APP = "pet-match-embed"


def meta_api_key() -> str:
    key = os.environ.get("MODEL_API_KEY")
    if key:
        return key
    for line in CREDENTIALS_FILE.read_text(encoding="utf-8").splitlines():
        if "meta" in line.lower():
            m = re.search(r"\S{20,}", line)
            if m:
                return m.group(0)
    raise RuntimeError(f"No Meta Model API key found in {CREDENTIALS_FILE}")


DATA.mkdir(exist_ok=True)
UPLOADS.mkdir(exist_ok=True)
