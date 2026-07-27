"""
db.py — SQLite storage. Local only; nothing leaves this machine.

Tables
------
messages: one row per newsletter (KEEP every newsletter).
  id           gmail message id (PK)
  sender, subject, received_at (epoch seconds), label
  created_at   when this row was first stored (epoch seconds)

links: one row per cleaned, deduped link found in a message.
  id           autoincrement
  message_id   FK -> messages.id
  url          cleaned/canonical URL
  anchor_text  visible link text
  snippet      surrounding text used for topical matching
  is_article   1 if it passed Gate 1 (real article link, not boilerplate)
  is_ai        1 if it passed Gate 2 (tech/AI topical match)
  score        0..1 relevance
  seen         app-side read flag (NEVER touches Gmail)
  UNIQUE(message_id, url)
"""

import sqlite3
from contextlib import contextmanager

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    sender      TEXT,
    subject     TEXT,
    received_at INTEGER,
    label       TEXT,
    created_at  INTEGER
);

CREATE TABLE IF NOT EXISTS links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  TEXT NOT NULL REFERENCES messages(id),
    url         TEXT NOT NULL,
    anchor_text TEXT,
    snippet     TEXT,
    is_article  INTEGER DEFAULT 1,
    is_ai       INTEGER DEFAULT 0,
    score       REAL DEFAULT 0,
    matched     TEXT DEFAULT '',
    seen        INTEGER DEFAULT 0,
    UNIQUE(message_id, url)
);

CREATE INDEX IF NOT EXISTS idx_links_message ON links(message_id);
CREATE INDEX IF NOT EXISTS idx_links_ai ON links(is_ai);
"""


@contextmanager
def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path):
    with connect(db_path) as conn:
        conn.executescript(_SCHEMA)
        # Lightweight migration: add columns introduced after first release.
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(links)")}
        if "matched" not in cols:
            conn.execute("ALTER TABLE links ADD COLUMN matched TEXT DEFAULT ''")


def upsert_message(conn, *, id, sender, subject, received_at, label, created_at):
    conn.execute(
        """INSERT INTO messages (id, sender, subject, received_at, label, created_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               sender=excluded.sender,
               subject=excluded.subject,
               received_at=excluded.received_at,
               label=excluded.label""",
        (id, sender, subject, received_at, label, created_at),
    )


def upsert_link(conn, *, message_id, url, anchor_text, snippet,
                is_article, is_ai, score, matched=""):
    """Insert a link, preserving the app-side `seen` flag on re-ingest.

    ON CONFLICT keeps the existing seen value (we only re-write classification
    fields), so a re-run never un-marks something you've already read.
    """
    conn.execute(
        """INSERT INTO links
             (message_id, url, anchor_text, snippet, is_article, is_ai, score, matched, seen)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
           ON CONFLICT(message_id, url) DO UPDATE SET
               anchor_text=excluded.anchor_text,
               snippet=excluded.snippet,
               is_article=excluded.is_article,
               is_ai=excluded.is_ai,
               score=excluded.score,
               matched=excluded.matched""",
        (message_id, url, anchor_text, snippet, is_article, is_ai, score, matched),
    )


def set_seen(db_path, link_id, seen):
    with connect(db_path) as conn:
        conn.execute("UPDATE links SET seen=? WHERE id=?", (1 if seen else 0, link_id))


def fetch_digest(db_path):
    """Return messages (newest data) each with their links, for the digest page."""
    with connect(db_path) as conn:
        messages = [dict(r) for r in conn.execute(
            "SELECT * FROM messages ORDER BY received_at DESC"
        )]
        links_by_msg = {}
        for r in conn.execute("SELECT * FROM links ORDER BY score DESC, id ASC"):
            links_by_msg.setdefault(r["message_id"], []).append(dict(r))
    for m in messages:
        m["links"] = links_by_msg.get(m["id"], [])
    return messages
