"""SQLite storage for groups, posts, photos, match verdicts and notifications.

Photo embeddings are stored as float32 blobs next to each photo row and
loaded into one NumPy matrix for searching.
"""
import json
import sqlite3
import threading

import numpy as np

from . import config

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    area TEXT NOT NULL,
    members INTEGER NOT NULL,
    opted_in INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id TEXT,
    poster TEXT NOT NULL,
    text TEXT NOT NULL,
    post_type TEXT NOT NULL,
    species TEXT NOT NULL,
    fields TEXT NOT NULL,
    lat REAL, lon REAL, radius_km REAL,
    event_date TEXT,
    created_at TEXT NOT NULL,
    contact_messenger TEXT, contact_phone TEXT, contact_email TEXT,
    demo_pet TEXT
);
CREATE TABLE IF NOT EXISTS photos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    crop_path TEXT NOT NULL,
    n_animals INTEGER NOT NULL,
    embedding BLOB,
    credit TEXT
);
CREATE TABLE IF NOT EXISTS verdicts (
    a INTEGER NOT NULL, b INTEGER NOT NULL, verdict TEXT NOT NULL,
    PRIMARY KEY (a, b)
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    match_post_id INTEGER NOT NULL,
    likelihood INTEGER NOT NULL,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (post_id, match_post_id)
);
"""


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


_db = connect()
_db.executescript(SCHEMA)


def q(sql: str, args=()) -> list[sqlite3.Row]:
    with _lock:
        return _db.execute(sql, args).fetchall()


def run(sql: str, args=()) -> int:
    with _lock:
        cur = _db.execute(sql, args)
        _db.commit()
        return cur.lastrowid


# Groups ----------------------------------------------------------------------

def groups() -> list[dict]:
    rows = q("""SELECT g.*, COUNT(p.id) AS posts FROM groups g
                LEFT JOIN posts p ON p.group_id = g.id GROUP BY g.id ORDER BY g.name""")
    return [dict(r) for r in rows]


def set_opt_in(group_id: str, opted_in: bool):
    run("UPDATE groups SET opted_in = ? WHERE id = ?", (int(opted_in), group_id))


def upsert_group(g: dict):
    run("""INSERT INTO groups (id, name, area, members, opted_in) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET name = excluded.name, area = excluded.area,
           members = excluded.members""",
        (g["id"], g["name"], g["area"], g["members"], int(g.get("opted_in", True))))


# Posts -----------------------------------------------------------------------

def add_post(p: dict) -> int:
    return run("""INSERT INTO posts (group_id, poster, text, post_type, species, fields,
                  lat, lon, radius_km, event_date, created_at,
                  contact_messenger, contact_phone, contact_email, demo_pet)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
               (p.get("group_id"), p["poster"], p["text"], p["post_type"], p["species"],
                json.dumps(p["fields"]), p.get("lat"), p.get("lon"), p.get("radius_km"),
                p.get("event_date"), p["created_at"], p.get("contact_messenger"),
                p.get("contact_phone"), p.get("contact_email"), p.get("demo_pet")))


def add_photo(post_id: int, path: str, crop_path: str, n_animals: int,
              embedding: np.ndarray, credit: dict | None = None):
    run("""INSERT INTO photos (post_id, path, crop_path, n_animals, embedding, credit)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (post_id, path, crop_path, n_animals,
         np.asarray(embedding, dtype=np.float32).tobytes(),
         json.dumps(credit) if credit else None))


def _post_dict(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["fields"] = json.loads(d["fields"])
    return d


def post(post_id: int) -> dict | None:
    rows = q("SELECT * FROM posts WHERE id = ?", (post_id,))
    return _post_dict(rows[0]) if rows else None


def searchable_posts() -> list[dict]:
    """Posts made directly in the feature plus posts from opted-in groups."""
    rows = q("""SELECT p.* FROM posts p LEFT JOIN groups g ON g.id = p.group_id
                WHERE p.group_id IS NULL OR g.opted_in = 1""")
    return [_post_dict(r) for r in rows]


def recent_posts(limit: int = 50) -> list[dict]:
    rows = q("""SELECT p.* FROM posts p LEFT JOIN groups g ON g.id = p.group_id
                WHERE p.group_id IS NULL OR g.opted_in = 1
                ORDER BY p.created_at DESC LIMIT ?""", (limit,))
    return [_post_dict(r) for r in rows]


def photos(post_id: int) -> list[dict]:
    rows = q("SELECT id, path, crop_path, n_animals, credit FROM photos WHERE post_id = ?",
             (post_id,))
    out = []
    for r in rows:
        d = dict(r)
        d["credit"] = json.loads(d["credit"]) if d["credit"] else None
        out.append(d)
    return out


def embeddings(post_ids: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """Matrix of photo embeddings for these posts and the post id of each row."""
    if not post_ids:
        return np.zeros((0, 0), np.float32), np.zeros(0, int)
    marks = ",".join("?" * len(post_ids))
    rows = q(f"SELECT post_id, embedding FROM photos WHERE embedding IS NOT NULL "
             f"AND post_id IN ({marks})", post_ids)
    if not rows:
        return np.zeros((0, 0), np.float32), np.zeros(0, int)
    mat = np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
    return mat, np.array([r["post_id"] for r in rows])


def post_embeddings(post_id: int) -> np.ndarray:
    rows = q("SELECT embedding FROM photos WHERE post_id = ? AND embedding IS NOT NULL",
             (post_id,))
    if not rows:
        return np.zeros((0, 0), np.float32)
    return np.stack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])


# Verdicts and notifications --------------------------------------------------

def cached_verdict(a: int, b: int) -> dict | None:
    a, b = sorted((a, b))
    rows = q("SELECT verdict FROM verdicts WHERE a = ? AND b = ?", (a, b))
    return json.loads(rows[0]["verdict"]) if rows else None


def save_verdict(a: int, b: int, verdict: dict):
    a, b = sorted((a, b))
    run("INSERT OR REPLACE INTO verdicts (a, b, verdict) VALUES (?, ?, ?)",
        (a, b, json.dumps(verdict)))


def notify(post_id: int, match_post_id: int, likelihood: int, summary: str, created_at: str):
    run("""INSERT OR IGNORE INTO notifications
           (post_id, match_post_id, likelihood, summary, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (post_id, match_post_id, likelihood, summary, created_at))


def notifications(limit: int = 30) -> list[dict]:
    rows = q("""SELECT n.*, p.poster, p.post_type FROM notifications n
                JOIN posts p ON p.id = n.post_id ORDER BY n.created_at DESC, n.id DESC
                LIMIT ?""", (limit,))
    return [dict(r) for r in rows]


def reset():
    with _lock:
        _db.executescript("""DROP TABLE IF EXISTS notifications; DROP TABLE IF EXISTS verdicts;
                             DROP TABLE IF EXISTS photos; DROP TABLE IF EXISTS posts;
                             DROP TABLE IF EXISTS groups;""")
        _db.executescript(SCHEMA)
        _db.commit()
