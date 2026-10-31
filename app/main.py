"""Web API and static front end for the pet matching demo.

Run with: python -m uvicorn app.main:app --port 8040
"""
import io
import uuid
from datetime import date

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from . import config, ingest, matching, meta_api, store

app = FastAPI(title="Pet Match")
WEB = config.ROOT / "web"
app.mount("/static", StaticFiles(directory=WEB), name="static")
# Only the demo post photos are served; the database and usage log stay private.
app.mount("/data/uploads", StaticFiles(directory=config.UPLOADS), name="uploads")

@app.middleware("http")
async def no_stale_pages(request: Request, call_next):
    """Make browsers check for a newer page and script on every visit, so a
    redeploy shows up straight away instead of an old cached copy."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


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


def _search_counts(visitor: str, ip: str) -> tuple[int, int]:
    return store.action_counts(date.today().isoformat(), "search", visitor, ip)


def _check_search_caps(visitor: str, ip: str):
    if not config.HOSTED:
        return
    if _over_budget():
        raise HTTPException(429, "The demo has reached its spending limit, so searching is "
                                 "switched off. You can still browse nearby posts.")
    mine, everyone = _search_counts(visitor, ip)
    if mine >= config.SEARCHES_PER_VISITOR_PER_DAY:
        raise HTTPException(429, f"You've run {mine} searches today, which is the daily limit "
                                 "for this demo. Come back tomorrow for more.")
    if everyone >= config.SEARCHES_PER_DAY:
        raise HTTPException(429, "The demo has run as many searches as it allows today. "
                                 "Please try again tomorrow.")


def _group_names() -> dict:
    return {g["id"]: g["name"] for g in store.groups()}


def post_view(p: dict, names: dict | None = None) -> dict:
    """A post as the page sees it. Contact details never leave the server;
    the page only learns whether the poster can be messaged."""
    names = names if names is not None else _group_names()
    f = p["fields"]
    return {
        "id": p["id"], "poster": p["poster"], "text": p["text"],
        "post_type": p["post_type"], "species": p["species"],
        "summary": f.get("summary", ""), "location": f.get("location_text", ""),
        "event_date": p["event_date"], "created_at": p["created_at"],
        "group": names.get(p["group_id"], "Lost and Found Pets"),
        "can_message": bool(p["contact_messenger"]),
        "photos": [{"url": "/data/" + ph["path"], "credit": ph["credit"]}
                   for ph in store.photos(p["id"])],
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


@app.get("/api/feed")
def feed(limit: int = 60):
    names = _group_names()
    return [post_view(p, names) for p in store.recent_posts(limit)]


def _demo_group() -> dict:
    group = next((g for g in store.groups() if g["id"] == config.OPT_IN_DEMO_GROUP), None)
    if group is None:
        raise HTTPException(404, "The opt-in demo group isn't set up.")
    return group


@app.get("/api/opt-in-demo")
def opt_in_demo():
    group = _demo_group()
    names = _group_names()
    rows = store.q("SELECT id FROM posts WHERE group_id = ? ORDER BY created_at DESC",
                   (config.OPT_IN_DEMO_GROUP,))
    return {**group, "posts": [post_view(store.post(r["id"]), names) for r in rows]}


class OptIn(BaseModel):
    opted_in: bool


@app.post("/api/opt-in-demo")
def set_opt_in_demo(body: OptIn):
    _demo_group()
    store.set_opt_in(config.OPT_IN_DEMO_GROUP, body.opted_in)
    after_write()
    return opt_in_demo()


@app.post("/api/search")
async def search(request: Request, response: Response, post_type: str = Form(...),
                 details: str = Form(""), photos: list[UploadFile] = File(...)):
    """Search every opted-in group with an upload. Nothing is stored."""
    visitor, ip = _visitor(request, response)
    _check_search_caps(visitor, ip)
    if post_type not in ("lost", "found"):
        raise HTTPException(400, "Choose whether you lost or found a pet.")
    files = [f for f in photos if f.filename]
    if not files:
        raise HTTPException(400, "Add a photo of the pet.")
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
    store.log_action(date.today().isoformat(), "search", visitor, ip)
    after_write()

    def run():
        me, vectors, crops = ingest.prepare_upload(details[:2000], images, post_type)
        return me, matching.search_upload(me, vectors, crops)

    me, results = await run_in_threadpool(run)
    names = _group_names()
    return {"query": {"post_type": post_type, "species": me["species"],
                      "summary": me["fields"].get("summary", "")},
            "matches": [match_view(r, names) for r in results]}


@app.get("/api/limits")
def limits(request: Request, response: Response):
    visitor, ip = _visitor(request, response)
    mine, everyone = _search_counts(visitor, ip)
    return {"hosted": config.HOSTED,
            "searches_left_today": max(0, config.SEARCHES_PER_VISITOR_PER_DAY - mine)
            if config.HOSTED else None,
            "search_open": not config.HOSTED or (not _over_budget()
                                                  and everyone < config.SEARCHES_PER_DAY)}
