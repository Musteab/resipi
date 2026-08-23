"""Tiny JSON-over-SQLite store, namespaced per browser session.

Every visitor gets their own `sid`, so concurrent judges running the demo at the
same time cannot reset or overwrite each other's run. One file, resettable per
session or globally.
"""
import json
import os
import sqlite3
import time

DB = os.environ.get("RESIPI_DB", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "var", "resipi.db"))
DEFAULT_NS = "shared"


def _conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.execute("PRAGMA journal_mode=WAL")  # concurrent readers while one writes
    c.execute("CREATE TABLE IF NOT EXISTS kv (ns TEXT, k TEXT, v TEXT, ts REAL, PRIMARY KEY (ns,k))")
    c.execute("CREATE TABLE IF NOT EXISTS conversations (ns TEXT, cid TEXT, state TEXT, ts REAL, PRIMARY KEY (ns,cid))")
    c.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, ns TEXT, ts REAL, kind TEXT, payload TEXT)")
    return c


def put(k, v, ns=DEFAULT_NS):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO kv VALUES (?,?,?,?)", (ns, k, json.dumps(v), time.time()))


def get(k, default=None, ns=DEFAULT_NS):
    with _conn() as c:
        r = c.execute("SELECT v FROM kv WHERE ns=? AND k=?", (ns, k)).fetchone()
    return json.loads(r[0]) if r else default


def drop(k, ns=DEFAULT_NS):
    with _conn() as c:
        c.execute("DELETE FROM kv WHERE ns=? AND k=?", (ns, k))


def save_conversation(cid, state, ns=DEFAULT_NS):
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO conversations VALUES (?,?,?,?)", (ns, cid, json.dumps(state), time.time()))


def load_conversation(cid, ns=DEFAULT_NS):
    with _conn() as c:
        r = c.execute("SELECT state FROM conversations WHERE ns=? AND cid=?", (ns, cid)).fetchone()
    return json.loads(r[0]) if r else None


def list_conversations(ns=DEFAULT_NS):
    with _conn() as c:
        rows = c.execute("SELECT cid, state FROM conversations WHERE ns=? ORDER BY ts DESC", (ns,)).fetchall()
    return [{"conversation_id": r[0], **json.loads(r[1])} for r in rows]


def log(kind, payload, ns=DEFAULT_NS):
    with _conn() as c:
        c.execute("INSERT INTO events (ns,ts,kind,payload) VALUES (?,?,?,?)", (ns, time.time(), kind, json.dumps(payload)))


def events(limit=200, ns=DEFAULT_NS):
    with _conn() as c:
        rows = c.execute("SELECT ts,kind,payload FROM events WHERE ns=? ORDER BY id DESC LIMIT ?", (ns, limit)).fetchall()
    return [{"ts": r[0], "kind": r[1], "payload": json.loads(r[2])} for r in rows]


def reset(ns=DEFAULT_NS):
    """Reset ONE session. Never touches another visitor's run."""
    with _conn() as c:
        for t in ("kv", "conversations", "events"):
            c.execute("DELETE FROM %s WHERE ns=?" % t, (ns,))


def sweep(max_age_seconds=6 * 3600):
    """Drop sessions nobody has touched in a while, so the demo file stays small."""
    cutoff = time.time() - max_age_seconds
    with _conn() as c:
        stale = [r[0] for r in c.execute("SELECT ns FROM kv GROUP BY ns HAVING MAX(ts) < ?", (cutoff,)).fetchall()]
        for ns in stale:
            for t in ("kv", "conversations", "events"):
                c.execute("DELETE FROM %s WHERE ns=?" % t, (ns,))
    return len(stale)
