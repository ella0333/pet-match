"""Turn the location a post mentions into a point plus an uncertainty radius.

Places in the demo town come from demo_data/town.json; anything else is
looked up on OpenStreetMap Nominatim.
"""
import json
import math
import time

import requests

from . import config

RADIUS_KM = {"address": 0.2, "street": 0.5, "neighbourhood": 1.5,
             "city": 8.0, "region": 40.0}
NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "pet-match-demo/0.1"}

_places = None
_cache: dict[str, tuple | None] = {}
_last_call = 0.0


def _gazetteer() -> dict:
    global _places
    if _places is None:
        _places = json.loads(config.TOWN_PATH.read_text(encoding="utf-8"))["places"]
    return _places


def _nominatim(text: str):
    global _last_call
    # Nominatim's usage policy allows one request per second.
    time.sleep(max(0.0, 1.0 - (time.time() - _last_call)))
    _last_call = time.time()
    try:
        r = requests.get(NOMINATIM, params={"q": text, "format": "json", "limit": 1},
                         headers=HEADERS, timeout=15)
        hits = r.json() if r.ok else []
    except requests.RequestException:
        hits = []
    if not hits:
        return None
    return float(hits[0]["lat"]), float(hits[0]["lon"])


def locate(text: str, precision: str):
    """Returns (lat, lon, radius_km) or None when the post gives no usable place."""
    text = (text or "").strip()
    if not text:
        return None
    key = text.lower()
    places = _gazetteer()
    hits = [name for name in places if name.lower() in key]
    if hits:
        # The most specific place mentioned wins ("Pine Street, Old Mill").
        name = min(hits, key=lambda n: RADIUS_KM.get(places[n]["kind"], 8.0))
        p = places[name]
        return p["lat"], p["lon"], RADIUS_KM.get(p["kind"], 8.0)
    if key not in _cache:
        _cache[key] = _nominatim(text)
    point = _cache[key]
    if point is None:
        return None
    return point[0], point[1], RADIUS_KM.get(precision, 8.0)


def distance_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(a))
