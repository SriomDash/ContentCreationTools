"""
Data layer — isolated behind the `Repository` interface.

All SQL lives here. Application code (ingest, topic, angles, pairing, main)
depends only on the `Repository` abstract methods and on the `Source`/`Article`
dataclasses — never on sqlite3 directly. To move to Postgres later, add a
`PostgresRepository(Repository)` alongside `SqliteRepository` and swap the
factory in `get_repository()`; no caller changes required.
"""
from __future__ import annotations

import abc
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import List, Optional

from .models import Article, Source

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "app.db")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------
class Repository(abc.ABC):
    # --- sources ---
    @abc.abstractmethod
    def add_source(self, source: Source) -> Source: ...
    @abc.abstractmethod
    def update_source(self, source: Source) -> None: ...
    @abc.abstractmethod
    def get_source(self, source_id: int) -> Optional[Source]: ...
    @abc.abstractmethod
    def get_source_by_url(self, url: str) -> Optional[Source]: ...
    @abc.abstractmethod
    def list_sources(self, include_disabled: bool = True) -> List[Source]: ...
    @abc.abstractmethod
    def delete_source(self, source_id: int) -> None: ...
    @abc.abstractmethod
    def set_source_status(self, source_id: int, status: str, error: Optional[str] = None,
                          touch_fetched: bool = False) -> None: ...

    # --- articles ---
    @abc.abstractmethod
    def upsert_article(self, article: Article) -> bool:
        """Insert if canonical_url is new. Returns True if newly inserted."""
    @abc.abstractmethod
    def list_articles(self, min_score: float = 0.0, angle: Optional[str] = None,
                      include_seen: bool = False, only_gate_passed: bool = True,
                      recent_days: Optional[int] = None, date: Optional[str] = None,
                      search: Optional[str] = None, starred_only: bool = False,
                      limit: int = 500) -> List[Article]: ...
    @abc.abstractmethod
    def get_article(self, article_id: int) -> Optional[Article]: ...
    @abc.abstractmethod
    def set_article_seen(self, article_id: int, seen: bool = True) -> None: ...
    @abc.abstractmethod
    def set_article_starred(self, article_id: int, starred: bool = True) -> None: ...
    @abc.abstractmethod
    def delete_articles_older_than(self, days: int) -> int:
        """Delete non-starred articles whose age (published_at, else created_at) exceeds `days`."""
    @abc.abstractmethod
    def active_dates(self, limit: int = 60) -> List[str]:
        """Distinct YYYY-MM-DD publish dates that have gate-passed articles, newest first."""
    @abc.abstractmethod
    def counts(self) -> dict: ...


# ---------------------------------------------------------------------------
# SQLite implementation
# ---------------------------------------------------------------------------
class SqliteRepository(Repository):
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        # check_same_thread=False + a lock: safe use across the scheduler thread
        # and FastAPI's threadpool without a per-request connection pool.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            self._conn.executescript(f.read())
        self._conn.commit()
        self._migrate()

    def _migrate(self) -> None:
        """Lightweight additive migrations for pre-existing databases."""
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(articles)")}
        if "starred" not in cols:
            self._conn.execute(
                "ALTER TABLE articles ADD COLUMN starred INTEGER NOT NULL DEFAULT 0"
            )
        # Create the starred index here (after the column is guaranteed to exist),
        # for both fresh and migrated databases.
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_starred ON articles(starred)")
        self._conn.commit()

    # -- row mappers --
    @staticmethod
    def _row_to_source(r: sqlite3.Row) -> Source:
        return Source(
            id=r["id"], url=r["url"], feed_url=r["feed_url"], name=r["name"],
            angle=r["angle"], type=r["type"], notes=r["notes"],
            is_paywall=bool(r["is_paywall"]), status=r["status"],
            last_fetched=r["last_fetched"], last_error=r["last_error"],
        )

    @staticmethod
    def _row_to_article(r: sqlite3.Row) -> Article:
        return Article(
            id=r["id"], canonical_url=r["canonical_url"], title=r["title"],
            summary=r["summary"], source_id=r["source_id"], published_at=r["published_at"],
            score=r["score"], passed_topic_gate=bool(r["passed_topic_gate"]),
            primary_angle=r["primary_angle"], angles=json.loads(r["angles"] or "[]"),
            is_critic=bool(r["is_critic"]), fingerprint=json.loads(r["fingerprint"] or "[]"),
            seen=bool(r["seen"]), starred=bool(r["starred"]), created_at=r["created_at"],
            source_name=r["source_name"] if "source_name" in r.keys() else None,
        )

    # -- sources --
    def add_source(self, s: Source) -> Source:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO sources (url, feed_url, name, angle, type, notes, is_paywall,
                                        status, last_fetched, last_error)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (s.url, s.feed_url, s.name, s.angle, s.type, s.notes, int(s.is_paywall),
                 s.status, s.last_fetched, s.last_error),
            )
            self._conn.commit()
            s.id = cur.lastrowid
            return s

    def update_source(self, s: Source) -> None:
        with self._lock:
            self._conn.execute(
                """UPDATE sources SET url=?, feed_url=?, name=?, angle=?, type=?, notes=?,
                                      is_paywall=?, status=?, last_fetched=?, last_error=?
                   WHERE id=?""",
                (s.url, s.feed_url, s.name, s.angle, s.type, s.notes, int(s.is_paywall),
                 s.status, s.last_fetched, s.last_error, s.id),
            )
            self._conn.commit()

    def get_source(self, source_id: int) -> Optional[Source]:
        r = self._conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        return self._row_to_source(r) if r else None

    def get_source_by_url(self, url: str) -> Optional[Source]:
        r = self._conn.execute("SELECT * FROM sources WHERE url=?", (url,)).fetchone()
        return self._row_to_source(r) if r else None

    def list_sources(self, include_disabled: bool = True) -> List[Source]:
        q = "SELECT * FROM sources"
        if not include_disabled:
            q += " WHERE status != 'disabled'"
        q += " ORDER BY name COLLATE NOCASE"
        return [self._row_to_source(r) for r in self._conn.execute(q).fetchall()]

    def delete_source(self, source_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM sources WHERE id=?", (source_id,))
            self._conn.commit()

    def set_source_status(self, source_id: int, status: str, error: Optional[str] = None,
                          touch_fetched: bool = False) -> None:
        with self._lock:
            if touch_fetched:
                self._conn.execute(
                    "UPDATE sources SET status=?, last_error=?, last_fetched=? WHERE id=?",
                    (status, error, _utcnow(), source_id),
                )
            else:
                self._conn.execute(
                    "UPDATE sources SET status=?, last_error=? WHERE id=?",
                    (status, error, source_id),
                )
            self._conn.commit()

    # -- articles --
    def upsert_article(self, a: Article) -> bool:
        with self._lock:
            existing = self._conn.execute(
                "SELECT id FROM articles WHERE canonical_url=?", (a.canonical_url,)
            ).fetchone()
            if existing:
                return False  # dedupe by canonical URL — keep first-seen metadata
            self._conn.execute(
                """INSERT INTO articles (canonical_url, title, summary, source_id, published_at,
                                         score, passed_topic_gate, primary_angle, angles,
                                         is_critic, fingerprint, seen, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (a.canonical_url, a.title, a.summary, a.source_id, a.published_at, a.score,
                 int(a.passed_topic_gate), a.primary_angle, json.dumps(a.angles),
                 int(a.is_critic), json.dumps(a.fingerprint), int(a.seen),
                 a.created_at or _utcnow()),
            )
            self._conn.commit()
            return True

    def list_articles(self, min_score: float = 0.0, angle: Optional[str] = None,
                      include_seen: bool = False, only_gate_passed: bool = True,
                      recent_days: Optional[int] = None, date: Optional[str] = None,
                      search: Optional[str] = None, starred_only: bool = False,
                      limit: int = 500) -> List[Article]:
        clauses = ["a.score >= ?"]
        params: list = [min_score]
        if only_gate_passed:
            clauses.append("a.passed_topic_gate = 1")
        if starred_only:
            # The saved library: show every starred item regardless of seen/age.
            clauses.append("a.starred = 1")
        elif not include_seen:
            clauses.append("a.seen = 0")
        if search:
            # Keyword search: each whitespace-separated term must appear (AND) in
            # the title or summary. Case-insensitive substring match, no LLM.
            for term in search.split():
                clauses.append("(a.title LIKE ? OR a.summary LIKE ?)")
                like = f"%{term}%"
                params.extend([like, like])
        if angle:
            if angle == "critic":
                clauses.append("a.is_critic = 1")
            else:
                # match primary OR any secondary angle (angles is a JSON array string)
                clauses.append("(a.primary_angle = ? OR a.angles LIKE ?)")
                params.extend([angle, f'%"{angle}"%'])
        if date:
            # Filter to a single publish day (UTC). published_at is ISO8601 (starts YYYY-MM-DD).
            # Fall back to created_at when an item has no published date.
            clauses.append("substr(COALESCE(a.published_at, a.created_at), 1, 10) = ?")
            params.append(date)
        if recent_days is not None:
            # published_at is ISO8601; compare lexicographically against cutoff.
            from datetime import timedelta
            cutoff = (datetime.now(timezone.utc) - timedelta(days=recent_days)).isoformat()
            clauses.append("(a.published_at IS NULL OR a.published_at >= ?)")
            params.append(cutoff)
        where = " AND ".join(clauses)
        q = f"""SELECT a.*, s.name AS source_name
                FROM articles a JOIN sources s ON s.id = a.source_id
                WHERE {where}
                ORDER BY a.score DESC, a.published_at DESC
                LIMIT ?"""
        params.append(limit)
        return [self._row_to_article(r) for r in self._conn.execute(q, params).fetchall()]

    def get_article(self, article_id: int) -> Optional[Article]:
        r = self._conn.execute(
            """SELECT a.*, s.name AS source_name FROM articles a
               JOIN sources s ON s.id = a.source_id WHERE a.id=?""", (article_id,)
        ).fetchone()
        return self._row_to_article(r) if r else None

    def set_article_seen(self, article_id: int, seen: bool = True) -> None:
        with self._lock:
            self._conn.execute("UPDATE articles SET seen=? WHERE id=?", (int(seen), article_id))
            self._conn.commit()

    def set_article_starred(self, article_id: int, starred: bool = True) -> None:
        with self._lock:
            self._conn.execute("UPDATE articles SET starred=? WHERE id=?", (int(starred), article_id))
            self._conn.commit()

    def delete_articles_older_than(self, days: int) -> int:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self._lock:
            # Starred articles are saved for reference and never auto-deleted.
            cur = self._conn.execute(
                "DELETE FROM articles WHERE starred = 0 AND COALESCE(published_at, created_at) < ?",
                (cutoff,),
            )
            self._conn.commit()
            return cur.rowcount

    def active_dates(self, limit: int = 60) -> List[str]:
        rows = self._conn.execute(
            """SELECT DISTINCT substr(COALESCE(published_at, created_at), 1, 10) AS d
               FROM articles WHERE passed_topic_gate = 1 AND d IS NOT NULL
               ORDER BY d DESC LIMIT ?""", (limit,)
        ).fetchall()
        return [r["d"] for r in rows if r["d"]]

    def counts(self) -> dict:
        c = self._conn.execute(
            """SELECT
                 (SELECT COUNT(*) FROM sources) AS sources,
                 (SELECT COUNT(*) FROM sources WHERE status='active') AS sources_active,
                 (SELECT COUNT(*) FROM sources WHERE status='blocked') AS sources_blocked,
                 (SELECT COUNT(*) FROM sources WHERE status='no_feed') AS sources_no_feed,
                 (SELECT COUNT(*) FROM articles) AS articles_total,
                 (SELECT COUNT(*) FROM articles WHERE passed_topic_gate=1) AS articles_passed,
                 (SELECT COUNT(*) FROM articles WHERE passed_topic_gate=1 AND seen=0) AS articles_unseen,
                 (SELECT COUNT(*) FROM articles WHERE is_critic=1) AS articles_critic,
                 (SELECT COUNT(*) FROM articles WHERE starred=1) AS articles_starred
            """
        ).fetchone()
        return dict(c)


# ---------------------------------------------------------------------------
# Factory — the single swap point for a different backend.
# ---------------------------------------------------------------------------
_repo_singleton: Optional[Repository] = None


def get_repository(db_path: str = DEFAULT_DB_PATH) -> Repository:
    global _repo_singleton
    if _repo_singleton is None:
        _repo_singleton = SqliteRepository(db_path)
    return _repo_singleton
