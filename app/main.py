"""Web API and static front end for the pet matching demo.

Run with: python -m uvicorn app.main:app --port 8040
"""
import io
import uuid
from datetime import date

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from PIL import Image
from pydantic import BaseModel

from . import config, ingest, matching, meta_api, store

app = FastAPI(title="Pet Match")
WEB = config.ROOT / "web"
app.mount("/static", StaticFiles(directory=WEB), name="static")
# Only the photos are served; the database and usage log stay private.
app.mount("/data/uploads", StaticFiles(directory=config.UPLOADS), name="uploads")

# Called after anything that writes, so the hosted app can persist its volume.
after_write = lambda: None  # noqa: E731

VISITOR_COOKIE = "pm_visitor"


def _visitor(request: Request, response: Response) -> tuple[str, str]:
    visitor = request.cookies.get(VISITOR_COOKIE)
    if not visitor:
        visitor = uuid.uuid4().hex
        response.set_cookie(VISITOR_COOKIE, visitor, max_age=60 * 60 * 24 * 30,
                            httponly=True, samesite="lax")
    forwarded = request.headers.get("x-forwarded-for", "")
    ip = forwarded.split(",")[0].strip() or (request.client.host if request.client else "")
    return visitor, ip


def _over_budget() -> bool:
    return config.HOSTED and meta_api.hosted_spend() >= config.SPEND_CEILING_USD


def _check_post_caps(visitor: str, ip: str):
    if not config.HOSTED:
        return
    if _over_budget():
        raise HTTPException(429, "The demo has reached its spending limit, so new posts are "
                                 "switched off. You can still browse and search.")
    mine, everyone = store.action_counts(date.today().isoformat(), "post", visitor, ip)
    if mine >= config.POSTS_PER_VISITOR_PER_DAY:
        raise HTTPException(429, f"You've added {mine} posts today, which is the daily "
                                 "limit for this demo. You can still browse and search.")
    if everyone >= config.POSTS_PER_DAY:
        raise HTTPException(429, "The demo has had as many new posts as it allows today. "
                                 "You can still browse and search.")


def _may_spend_on_search(visitor: str, ip: str) -> bool:
    if not config.HOSTED:
        return True
    if _over_budget():
        return False
    mine, everyone = store.action_counts(date.today().isoformat(), "search", visitor, ip)
    return mine < config.NEW_SEARCHES_PER_VISITOR_PER_DAY and everyone < config.NEW_SEARCHES_PER_DAY


def _group_names() -> dict:
    return {g["id"]: g["name"] for g in store.groups()}


def post_view(p: dict, names: dict | None = None) -> dict:
    names = names if names is not None else _group_names()
    f = p["fields"]
    return {
        "id": p["id"], "poster": p["poster"], "text": p["text"],
        "post_type": p["post_type"], "species": p["species"],
        "summary": f.get("summary", ""), "location": f.get("location_text", ""),
        "event_date": p["event_date"], "created_at": p["created_at"],
        "group": names.get(p["group_id"], "Posted in Lost and Found Pets"),
        "contact": {"messenger": p["contact_messenger"], "phone": p["contact_phone"],
                    "email": p["contact_email"]},
        "photos": [{"url": "/data/" + ph["path"], "crop": "/data/" + ph["crop_path"],
                    "credit": ph["credit"]} for ph in store.photos(p["id"])],
    }


def match_view(r: dict, names: dict) -> dict:
    out = {"post": post_view(r["post"], names), "combined": round(r["combined"], 3),
           "scores": {k: round(v, 3) for k, v in r["scores"].items()},
           "gap_km": None if r["gap_km"] is None else round(r["gap_km"], 1),
           "days": r["days"]}
    if "verdict" in r:
        out["verdict"] = r["verdict"]
    return out


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/api/groups")
def list_groups():
    return store.groups()


class OptIn(BaseModel):
    opted_in: bool


@app.post("/api/groups/{group_id}/opt-in")
def opt_in(group_id: str, body: OptIn):
    store.set_opt_in(group_id, body.opted_in)
    after_write()
    return store.groups()


@app.post("/api/reset")
def reset_demo():
    if not config.SNAPSHOT_PATH.exists():
        raise HTTPException(404, "No saved demo to reset to.")
    store.restore_snapshot()
    after_write()
    return {"ok": True}


@app.get("/api/feed")
def feed(limit: int = 40):
    names = _group_names()
    return [post_view(p, names) for p in store.recent_posts(limit)]


@app.get("/api/posts/{post_id}")
def get_post(post_id: int):
    p = store.post(post_id)
    if p is None:
        raise HTTPException(404)
    return post_view(p)


@app.get("/api/posts/{post_id}/matches")
def get_matches(post_id: int, request: Request, response: Response):
    if store.post(post_id) is None:
        raise HTTPException(404)
    visitor, ip = _visitor(request, response)
    allow_new = _may_spend_on_search(visitor, ip)
    before = store.q("SELECT COUNT(*) AS n FROM verdicts")[0]["n"]
    results = matching.find_matches(post_id, allow_new=allow_new)
    if store.q("SELECT COUNT(*) AS n FROM verdicts")[0]["n"] > before:
        store.log_action(date.today().isoformat(), "search", visitor, ip)
        after_write()
    names = _group_names()
    return [match_view(r, names) for r in results]


@app.post("/api/posts")
async def create_post(request: Request, response: Response,
                      text: str = Form(...), post_type: str = Form(...),
                      poster: str = Form("You"), messenger: str = Form(""),
                      phone: str = Form(""), email: str = Form(""),
                      photos: list[UploadFile] = File(...)):
    visitor, ip = _visitor(request, response)
    _check_post_caps(visitor, ip)
    if post_type not in ("lost", "found"):
        raise HTTPException(400, "Choose lost or found.")
    files = [f for f in photos if f.filename]
    if not files:
        raise HTTPException(400, "Add at least one photo.")
    if len(files) > config.MAX_PHOTOS:
        raise HTTPException(400, f"Add up to {config.MAX_PHOTOS} photos.")
    images = []
    for f in files:
        data = await f.read(config.MAX_PHOTO_BYTES + 1)
        if len(data) > config.MAX_PHOTO_BYTES:
            raise HTTPException(400, "Each photo can be up to 10 MB.")
        try:
            Image.open(io.BytesIO(data)).verify()
        except Exception:
            raise HTTPException(400, "One of the files isn't a photo we can read.")
        images.append(data)
    store.log_action(date.today().isoformat(), "post", visitor, ip)
    post_id = await run_in_threadpool(
        ingest.ingest_post, text[:2000], images, poster[:60] or "You", post_type=post_type,
        contact_messenger=messenger[:80], contact_phone=phone[:40], contact_email=email[:120])
    after_write()
    return {"id": post_id}


@app.get("/api/limits")
def limits(request: Request, response: Response):
    visitor, ip = _visitor(request, response)
    today = date.today().isoformat()
    mine, everyone = store.action_counts(today, "post", visitor, ip)
    return {"hosted": config.HOSTED,
            "posts_left_today": max(0, config.POSTS_PER_VISITOR_PER_DAY - mine)
            if config.HOSTED else None,
            "posting_open": not config.HOSTED or (not _over_budget()
                                                   and everyone < config.POSTS_PER_DAY)}


@app.get("/api/notifications")
def notifications():
    names = _group_names()
    out = []
    for n in store.notifications():
        match = store.post(n["match_post_id"])
        out.append({**n, "match": post_view(match, names) if match else None})
    return out
