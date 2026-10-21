"""Web API and static front end for the pet matching demo.

Run with: python -m uvicorn app.main:app --port 8040
"""
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, ingest, matching, store

app = FastAPI(title="Pet Match")
WEB = config.ROOT / "web"
app.mount("/static", StaticFiles(directory=WEB), name="static")
app.mount("/data", StaticFiles(directory=config.DATA), name="data")


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
        "photos": [{"url": "/" + ph["path"], "crop": "/" + ph["crop_path"],
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
    return store.groups()


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
def get_matches(post_id: int, rerank: bool = True):
    if store.post(post_id) is None:
        raise HTTPException(404)
    names = _group_names()
    return [match_view(r, names) for r in matching.find_matches(post_id, rerank=rerank)]


@app.post("/api/posts")
async def create_post(text: str = Form(...), post_type: str = Form(...),
                      poster: str = Form("You"), messenger: str = Form(""),
                      phone: str = Form(""), email: str = Form(""),
                      photos: list[UploadFile] = File(...)):
    images = [await f.read() for f in photos if f.filename]
    if not images:
        raise HTTPException(400, "Add at least one photo.")
    post_id = ingest.ingest_post(text, images[:6], poster, post_type=post_type,
                                 contact_messenger=messenger, contact_phone=phone,
                                 contact_email=email)
    return {"id": post_id}


@app.get("/api/notifications")
def notifications():
    names = _group_names()
    out = []
    for n in store.notifications():
        match = store.post(n["match_post_id"])
        out.append({**n, "match": post_view(match, names) if match else None})
    return out
