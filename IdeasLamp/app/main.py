"""
FastAPI app: dashboard + JSON API.

Startup: init DB, seed sources.csv, start the 3h scheduler, kick off one
background fetch so the feed populates on first run.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, digest, ingest, pairing, scheduler, seed
from .db import get_repository
from .models import Source

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ideaslamp")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

app = FastAPI(title="IdeasLamp", description="Personal AI content-research aggregator")
repo = get_repository()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@app.on_event("startup")
def _startup() -> None:
    n = seed.seed_sources(repo)
    log.info("startup: %d sources seeded (new)", n)
    scheduler.start_scheduler(repo)
    # Kick an initial fetch in the background so the feed fills without blocking startup.
    import threading
    threading.Thread(target=lambda: ingest.fetch_all(repo), daemon=True).start()


@app.on_event("shutdown")
def _shutdown() -> None:
    scheduler.shutdown_scheduler()


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------
def _article_json(a) -> dict:
    return {
        "id": a.id, "title": a.title, "summary": a.summary, "url": a.canonical_url,
        "source": a.source_name, "source_id": a.source_id,
        "published_at": a.published_at, "score": a.score,
        "primary_angle": a.primary_angle, "angles": a.angles,
        "is_critic": a.is_critic, "seen": a.seen, "starred": a.starred,
    }


def _source_json(s: Source) -> dict:
    return {
        "id": s.id, "url": s.url, "feed_url": s.feed_url, "name": s.name,
        "angle": s.angle, "type": s.type, "notes": s.notes,
        "is_paywall": s.is_paywall, "status": s.status,
        "last_fetched": s.last_fetched, "last_error": s.last_error,
    }


# ---------------------------------------------------------------------------
# Feed
# ---------------------------------------------------------------------------
@app.get("/api/feed")
def get_feed(min_score: float = 0.0, angle: Optional[str] = None,
             include_seen: bool = False, recent_only: bool = False,
             date: Optional[str] = None, search: Optional[str] = None,
             starred_only: bool = False):
    recent_days = config.SETTINGS["recent_days"] if recent_only else None
    arts = repo.list_articles(
        min_score=min_score, angle=angle, include_seen=include_seen,
        only_gate_passed=True, recent_days=recent_days, date=date,
        search=search, starred_only=starred_only, limit=500,
    )
    return {"count": len(arts), "articles": [_article_json(a) for a in arts]}


@app.get("/api/dates")
def get_dates():
    """Distinct publish dates that have articles (for the date picker)."""
    return {"dates": repo.active_dates(limit=90)}


@app.get("/api/digest")
def get_digest(date: Optional[str] = None):
    """Topic digest for a day: angle breakdown + top keywords."""
    return {"digest": digest.daily_digest(repo, date=date)}


@app.post("/api/articles/{article_id}/seen")
def mark_seen(article_id: int, seen: bool = True):
    if not repo.get_article(article_id):
        raise HTTPException(404, "article not found")
    repo.set_article_seen(article_id, seen)
    return {"ok": True, "id": article_id, "seen": seen}


@app.post("/api/articles/{article_id}/star")
def mark_starred(article_id: int, starred: bool = True):
    if not repo.get_article(article_id):
        raise HTTPException(404, "article not found")
    repo.set_article_starred(article_id, starred)
    return {"ok": True, "id": article_id, "starred": starred}


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
class AddSource(BaseModel):
    url: str
    angle: str = "tech"


@app.get("/api/sources")
def get_sources():
    return {"sources": [_source_json(s) for s in repo.list_sources(include_disabled=True)]}


@app.post("/api/sources")
def add_source(body: AddSource, background: BackgroundTasks):
    url = body.url.strip()
    if not url.lower().startswith("http"):
        url = "https://" + url
    if repo.get_source_by_url(url):
        raise HTTPException(409, "source already exists")

    from urllib.parse import urlparse
    name = urlparse(url).netloc.replace("www.", "") or url
    src = Source(id=None, url=url, feed_url=None, name=name,
                 angle=body.angle.strip().lower(), type="user-added", notes="",
                 is_paywall=False, status="active")
    src = repo.add_source(src)
    # Immediate background fetch (resolves feed + robots check inside fetch_source).
    background.add_task(ingest.fetch_source, repo, src)
    return {"ok": True, "source": _source_json(src)}


@app.delete("/api/sources/{source_id}")
def delete_source(source_id: int):
    if not repo.get_source(source_id):
        raise HTTPException(404, "source not found")
    repo.delete_source(source_id)
    return {"ok": True}


@app.post("/api/sources/{source_id}/status")
def set_status(source_id: int, status: str):
    src = repo.get_source(source_id)
    if not src:
        raise HTTPException(404, "source not found")
    if status not in ("active", "disabled"):
        raise HTTPException(400, "status must be 'active' or 'disabled'")
    repo.set_source_status(source_id, status, None)
    return {"ok": True, "status": status}


@app.post("/api/sources/{source_id}/refetch")
def refetch(source_id: int, background: BackgroundTasks):
    src = repo.get_source(source_id)
    if not src:
        raise HTTPException(404, "source not found")
    background.add_task(ingest.fetch_source, repo, src)
    return {"ok": True}


@app.post("/api/fetch")
def fetch_now(background: BackgroundTasks):
    background.add_task(ingest.fetch_all, repo)
    return {"ok": True, "message": "fetch started in background"}


@app.post("/api/prune")
def prune_now():
    """Manually run the retention cleanup (same as the nightly job)."""
    deleted = scheduler.run_retention_cleanup(repo)
    return {"ok": True, "deleted": deleted, "retention_days": config.SETTINGS["retention_days"]}


# ---------------------------------------------------------------------------
# Pairing
# ---------------------------------------------------------------------------
@app.get("/api/pairing")
def get_pairing(mode: str = "cross", offset: int = 0, lock_id: Optional[int] = None,
                min_score: Optional[float] = None):
    if mode not in ("cross", "critic"):
        raise HTTPException(400, "mode must be 'cross' or 'critic'")
    result = pairing.find_pairing(repo, mode=mode, offset=offset,
                                  lock_id=lock_id, min_score=min_score)
    if result is None:
        return JSONResponse({"pairing": None,
                             "message": "No eligible pairing found. Try a lower min-relevance, "
                                        "clear the lock, or fetch more sources."})
    return {"pairing": result}


# ---------------------------------------------------------------------------
# Stats + static
# ---------------------------------------------------------------------------
@app.get("/api/stats")
def stats():
    return {"counts": repo.counts(), "angles": config.ALL_ANGLES,
            "critic_angle": config.CRITIC_ANGLE,
            "default_min_relevance": config.SETTINGS["default_min_relevance"]}


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
