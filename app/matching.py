"""Rank posts of the opposite type by how likely they show the same animal.

1. Hard rules drop impossible pairs (type, species, dates, travel distance).
2. A combined score ranks the rest: DINOv3 photo similarity, description
   agreement, distance and time, equally weighted.
3. Muse Spark looks at the top candidates side by side; its likelihood sets
   the final order and its reasons are shown to the user.
"""
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np

from . import config, geo, meta_api, store

WEIGHTS = {"photo": 1.0, "description": 1.0, "distance": 1.0, "time": 1.0}
RERANK_TOP = 10
DATE_GRACE_DAYS = 1
NOTIFY_LIKELIHOOD = 70

# How far a pet plausibly gets from where it went missing: a base radius
# plus a daily drift, capped. Cats tend to stay much closer than dogs.
TRAVEL_KM = {"cat": (3.0, 0.5, 20.0), "dog": (8.0, 3.0, 80.0), "other": (8.0, 3.0, 80.0)}


def _date(s: str | None) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def _lost_found(a: dict, b: dict) -> tuple[dict, dict]:
    return (a, b) if a["post_type"] == "lost" else (b, a)


def _days_between(a: dict, b: dict) -> int | None:
    lost, found = _lost_found(a, b)
    ld, fd = _date(lost["event_date"]), _date(found["event_date"])
    if not ld or not fd:
        return None
    return (fd - ld).days


def _max_travel(species: str, days: int | None) -> float:
    base, per_day, cap = TRAVEL_KM.get(species, TRAVEL_KM["other"])
    return min(cap, base + per_day * max(1, days if days is not None else 14))


def _gap_km(a: dict, b: dict) -> float | None:
    if a["lat"] is None or b["lat"] is None:
        return None
    d = geo.distance_km(a["lat"], a["lon"], b["lat"], b["lon"])
    return max(0.0, d - (a["radius_km"] or 0) - (b["radius_km"] or 0))


def passes_rules(a: dict, b: dict) -> bool:
    if a["id"] == b["id"]:
        return False
    if {a["post_type"], b["post_type"]} != {"lost", "found"}:
        return False
    if a["species"] != b["species"]:
        return False
    days = _days_between(a, b)
    # A pet found before it went missing is not that pet.
    if days is not None and days < -DATE_GRACE_DAYS:
        return False
    gap = _gap_km(a, b)
    if gap is not None and gap > _max_travel(a["species"], days):
        return False
    return True


def _words(items) -> set[str]:
    out = set()
    for item in items or []:
        out.update(w for w in item.lower().replace("-", " ").split() if len(w) > 2)
    return out


def description_score(fa: dict, fb: dict) -> float:
    parts = []
    ca, cb = _words(fa.get("colors")), _words(fb.get("colors"))
    if ca and cb:
        parts.append(len(ca & cb) / len(ca | cb))
    ma = _words(fa.get("markings")) | _words([fa.get("pattern", "")])
    mb = _words(fb.get("markings")) | _words([fb.get("pattern", "")])
    if ma and mb:
        parts.append(len(ma & mb) / len(ma | mb))
    if "unknown" not in (fa.get("sex"), fb.get("sex")):
        parts.append(1.0 if fa["sex"] == fb["sex"] else 0.0)
    if "unknown" not in (fa.get("size"), fb.get("size")):
        parts.append(1.0 if fa["size"] == fb["size"] else 0.3)
    return float(np.mean(parts)) if parts else 0.5


def score_pair(a: dict, b: dict, emb_a: np.ndarray, emb_b: np.ndarray) -> dict:
    scores = {}
    if emb_a.size and emb_b.size:
        scores["photo"] = float(np.clip((emb_a @ emb_b.T).max(), 0, 1))
    else:
        scores["photo"] = 0.0
    scores["description"] = description_score(a["fields"], b["fields"])
    days = _days_between(a, b)
    gap = _gap_km(a, b)
    if gap is None:
        scores["distance"] = 0.5
    else:
        scores["distance"] = math.exp(-gap / _max_travel(a["species"], days))
    scores["time"] = 0.5 if days is None else math.exp(-max(0, days) / 45)
    total = sum(WEIGHTS[k] * v for k, v in scores.items()) / sum(WEIGHTS.values())
    return {"scores": scores, "combined": total, "gap_km": gap, "days": days}


def _crop_bytes(post_id: int) -> list[bytes]:
    return [(config.DATA / p["crop_path"]).read_bytes() for p in store.photos(post_id)]


def verdict_for(a: dict, b: dict, allow_new: bool = True) -> dict | None:
    cached = store.cached_verdict(a["id"], b["id"])
    if cached or not allow_new:
        return cached
    v = meta_api.compare_posts(a, b, _crop_bytes(a["id"]), _crop_bytes(b["id"]))
    store.save_verdict(a["id"], b["id"], v)
    return v


def _rank(me: dict, mine: np.ndarray, top: int) -> list[dict]:
    """Top candidates by the combined score, before the Muse Spark check."""
    pool = [p for p in store.searchable_posts() if passes_rules(me, p)]
    if not pool:
        return []
    mat, owners = store.embeddings([p["id"] for p in pool])
    results = []
    for p in pool:
        theirs = mat[owners == p["id"]] if mat.size else np.zeros((0, 0), np.float32)
        r = score_pair(me, p, mine, theirs)
        r["post"] = p
        results.append(r)
    results.sort(key=lambda r: r["combined"], reverse=True)
    return results[:top]


def _check(results: list[dict], verdict) -> list[dict]:
    """Run the Muse Spark check on every candidate and order by its likelihood.

    The checks are independent, so they run together and a search takes about
    as long as one call."""
    with ThreadPoolExecutor(max_workers=RERANK_TOP) as pool_:
        verdicts = list(pool_.map(verdict, results))
    for r, v in zip(results, verdicts):
        if v:
            r["verdict"] = v
    results.sort(key=lambda r: ("verdict" in r,
                                r["verdict"]["same_pet_likelihood"] if "verdict" in r else 0,
                                r["combined"]), reverse=True)
    return results


def find_matches(post_id: int, rerank: bool = True, top: int = RERANK_TOP,
                 allow_new: bool = True) -> list[dict]:
    """Ranked candidates for a stored post. With allow_new off, only saved
    Muse Spark checks are used, so the search makes no paid calls."""
    me = store.post(post_id)
    if me is None:
        return []
    results = _rank(me, store.post_embeddings(post_id), top)
    if rerank:
        results = _check(results, lambda r: verdict_for(me, r["post"], allow_new))
    return results


def search_upload(me: dict, mine: np.ndarray, my_crops: list[bytes], check: bool = True,
                  top: int = RERANK_TOP) -> list[dict]:
    """Ranked candidates for an upload that is never stored. `me` is the
    post-shaped dict from ingest.prepare_upload, with id -1."""
    def verdict(r):
        try:
            return meta_api.compare_posts(me, r["post"], my_crops, _crop_bytes(r["post"]["id"]))
        except Exception:
            # One failed check shouldn't sink the search; that result just
            # shows without Muse Spark's reasons.
            return None

    results = _rank(me, mine, top)
    if check:
        results = _check(results, verdict)
    return results


def notify_matches(post_id: int, created_at: str, top: int = 3):
    """Tell the owners of strongly matching existing posts about a new post."""
    for r in find_matches(post_id, rerank=True, top=top):
        v = r.get("verdict")
        if v and v["same_pet_likelihood"] >= NOTIFY_LIKELIHOOD:
            store.notify(r["post"]["id"], post_id, v["same_pet_likelihood"],
                         v["summary"], created_at)
