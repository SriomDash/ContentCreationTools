-- IdeasLamp schema. Kept intentionally portable (works on SQLite; the only
-- SQLite-specific choice is AUTOINCREMENT, trivially swapped for SERIAL/IDENTITY
-- when moving to Postgres). All access goes through app/db.py (Repository).

CREATE TABLE IF NOT EXISTS sources (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    url           TEXT NOT NULL UNIQUE,
    feed_url      TEXT,
    name          TEXT NOT NULL,
    angle         TEXT NOT NULL,
    type          TEXT DEFAULT '',
    notes         TEXT DEFAULT '',
    is_paywall    INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'active',   -- active | blocked | no_feed | disabled
    last_fetched  TEXT,
    last_error    TEXT
);

CREATE TABLE IF NOT EXISTS articles (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_url     TEXT NOT NULL UNIQUE,
    title             TEXT NOT NULL,
    summary           TEXT DEFAULT '',
    source_id         INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    published_at      TEXT,
    score             REAL NOT NULL DEFAULT 0.0,
    passed_topic_gate INTEGER NOT NULL DEFAULT 0,
    primary_angle     TEXT NOT NULL DEFAULT 'tech',
    angles            TEXT NOT NULL DEFAULT '[]',   -- JSON array of angle strings
    is_critic         INTEGER NOT NULL DEFAULT 0,
    fingerprint       TEXT NOT NULL DEFAULT '[]',   -- JSON array of pairing keywords
    seen              INTEGER NOT NULL DEFAULT 0,
    starred           INTEGER NOT NULL DEFAULT 0,   -- saved for reference; exempt from retention prune
    created_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_articles_score      ON articles(score DESC);
CREATE INDEX IF NOT EXISTS idx_articles_published  ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_gate       ON articles(passed_topic_gate);
CREATE INDEX IF NOT EXISTS idx_articles_source     ON articles(source_id);
-- NOTE: idx_articles_starred is created in db.py _migrate() so that opening a
-- pre-'starred' database adds the column before the index references it.
