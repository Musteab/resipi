"""Tiny JSON-over-SQLite store. One file, resettable in one call."""
import json
import os
import sqlite3
import time

DB = os.environ.get("RESIPI_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "var", "resipi.db"))


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT, ts REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS conversations (cid TEXT PRIMARY KEY, state TEXT, ts REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, kind TEXT, payload TEXT)")
    return c


def put(k, v):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO kv VALUES (?,?,?)", (k, json.dumps(v), time.time()))


def get(k, default=None):
    with _conn() as c:
        r = c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return json.loads(r[0]) if r else default


def drop(k):
    with _conn() as c:
        c.execute("DELETE FROM kv WHERE k=?", (k,))


def save_conversation(cid, state):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO conversations VALUES (?,?,?)", (cid, json.dumps(state), time.time()))


def load_conversation(cid):
    with _conn() as c:
        r = c.execute("SELECT state FROM conversations WHERE cid=?", (cid,)).fetchone()
    return json.loads(r[0]) if r else None


def list_conversations():
    with _conn() as c:
        rows = c.execute("SELECT cid, state FROM conversations ORDER BY ts DESC").fetchall()
    return [{"conversation_id": r[0], **json.loads(r[1])} for r in rows]


def log(kind, payload):
    with _conn() as c:
        c.execute("INSERT INTO events (ts,kind,payload) VALUES (?,?,?)", (time.time(), kind, json.dumps(payload)))


def events(limit=200):
    with _conn() as c:
        rows = c.execute("SELECT ts,kind,payload FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{"ts": r[0], "kind": r[1], "payload": json.loads(r[2])} for r in rows]


def reset():
    """Full demo reset: wipe every table but keep the file/schema."""
    with _conn() as c:
        for t in ("kv", "conversations", "events"):
            c.execute("DELETE FROM " + t)
