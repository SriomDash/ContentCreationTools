"""
Ingestion: feed resolution, robots.txt compliance, polite fetching, and the
per-item pipeline (topic gate -> score -> angle tagging -> store).

COMPLIANCE (see README):
  * Metadata only. We store title, short summary/excerpt, source, published
    date, canonical link. We NEVER fetch or store article bodies / full-page
    HTML — not for paywalled items, not for anyone.
  * robots.txt is checked before any HTTP fetch (feed or scrape). Disallowed
    -> we do not fetch and mark the source 'blocked'.
  * Honest identifying User-Agent (config). No browser spoofing.
  * Per-domain rate limiting. Feeds are preferred over scraping.
  * On 403/429/robots-disallow/error -> status 'blocked' (or 'no_feed'),
    surfaced on the dashboard, never silently dropped.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import feedparser
import requests
from bs4 import BeautifulSoup

from . import angles as angle_mod
from . import config
from . import topic
from .db import Repository
from .models import Article, Source

log = logging.getLogger("ideaslamp.ingest")

UA = config.SETTINGS["user_agent"]
TIMEOUT = config.SETTINGS["http_timeout_seconds"]

# Per-domain rate limiting + robots cache (shared across threads).
_domain_last_hit: dict = {}
_robots_cache: dict = {}
_rate_lock = threading.Lock()


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def _polite_wait(url: str) -> None:
    delay = config.SETTINGS["per_domain_delay_seconds"]
    dom = _domain(url)
    with _rate_lock:
        last = _domain_last_hit.get(dom, 0.0)
        wait = delay - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        _domain_last_hit[dom] = time.time()


def _robots(url: str) -> RobotFileParser:
    dom = _domain(url)
    if dom in _robots_cache:
        return _robots_cache[dom]
    scheme = urlparse(url).scheme or "https"
    robots_url = f"{scheme}://{dom}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        _polite_wait(robots_url)
        resp = requests.get(robots_url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        if resp.status_code == 200:
            rp.parse(resp.text.splitlines())
        else:
            # No robots.txt (404 etc.) is conventionally treated as "allow all".
            rp.parse([])
    except requests.RequestException as e:
        log.warning("robots.txt fetch failed for %s: %s (treating as allow)", dom, e)
        rp.parse([])
    _robots_cache[dom] = rp
    return rp


def robots_allows(url: str) -> bool:
    try:
        return _robots(url).can_fetch(UA, url)
    except Exception:
        return True  # be permissive only on parser error, never on an explicit Disallow


def _http_get(url: str) -> requests.Response:
    _polite_wait(url)
    return requests.get(url, headers={"User-Agent": UA, "Accept": "*/*"}, timeout=TIMEOUT)


# ---------------------------------------------------------------------------
# Feed resolution
# ---------------------------------------------------------------------------
def _looks_like_feed(parsed) -> bool:
    return bool(getattr(parsed, "entries", None)) and not parsed.bozo or bool(
        getattr(parsed, "entries", None)
    )


def resolve_feed(url: str) -> Tuple[Optional[str], str]:
    """
    Try to find an RSS/Atom feed for a source URL.
    Returns (feed_url_or_None, note). Honors robots.txt for every fetch.
    Strategy: (1) is the URL itself a feed? (2) <link rel=alternate> in the HTML,
    (3) common feed paths.
    """
    if not robots_allows(url):
        return None, "robots-disallow"

    # (1) URL might already be a feed.
    try:
        r = _http_get(url)
        if r.status_code in (403, 429):
            return None, f"http-{r.status_code}"
        ctype = r.headers.get("Content-Type", "").lower()
        if any(t in ctype for t in ("xml", "rss", "atom")):
            parsed = feedparser.parse(r.content)
            if getattr(parsed, "entries", None):
                return url, "url-is-feed"
        # (2) parse HTML for <link rel="alternate" type="application/rss+xml">
        if "html" in ctype or "<html" in r.text[:2000].lower():
            soup = BeautifulSoup(r.text, "html.parser")
            for link in soup.find_all("link", rel=lambda v: v and "alternate" in v):
                t = (link.get("type") or "").lower()
                if "rss" in t or "atom" in t or "xml" in t:
                    href = link.get("href")
                    if href:
                        return urljoin(url, href), "html-alternate"
    except requests.RequestException as e:
        log.info("feed probe (direct) failed for %s: %s", url, e)

    # (3) common feed paths.
    base = f"{urlparse(url).scheme or 'https'}://{_domain(url)}"
    for path in config.SETTINGS["feed_probe_paths"]:
        candidate = urljoin(base + "/", path.lstrip("/"))
        if not robots_allows(candidate):
            continue
        try:
            r = _http_get(candidate)
            if r.status_code == 200:
                parsed = feedparser.parse(r.content)
                if getattr(parsed, "entries", None):
                    return candidate, f"probe:{path}"
        except requests.RequestException:
            continue
    return None, "no-feed-found"


# ---------------------------------------------------------------------------
# Item extraction (METADATA ONLY)
# ---------------------------------------------------------------------------
def _clean_summary(raw_html: str) -> str:
    if not raw_html:
        return ""
    text = BeautifulSoup(raw_html, "html.parser").get_text(" ", strip=True)
    limit = config.SETTINGS["summary_max_chars"]
    return text[:limit].strip()


def _entry_published(entry) -> Optional[str]:
    for key in ("published_parsed", "updated_parsed"):
        tm = entry.get(key)
        if tm:
            try:
                return datetime(*tm[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
    return None


def _canonical(entry) -> Optional[str]:
    link = entry.get("link")
    if not link and entry.get("links"):
        link = entry["links"][0].get("href")
    if not link:
        return None
    # Strip common tracking query fragments minimally; keep path canonical.
    parsed = urlparse(link)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/") or link


def parse_feed_entries(feed_url: str) -> List[dict]:
    """Fetch + parse a feed into metadata dicts. Never stores full bodies."""
    r = _http_get(feed_url)
    if r.status_code in (403, 429):
        raise PermissionError(f"http-{r.status_code}")
    parsed = feedparser.parse(r.content)
    out = []
    for e in parsed.entries[: config.SETTINGS["max_items_per_feed"]]:
        url = _canonical(e)
        if not url:
            continue
        title = (e.get("title") or "").strip()
        summary = _clean_summary(e.get("summary") or e.get("description") or "")
        out.append({"canonical_url": url, "title": title, "summary": summary,
                    "published_at": _entry_published(e)})
    return out


def scrape_links(url: str) -> List[dict]:
    """
    Minimal polite fallback when there is no feed AND robots allows.
    Extracts links + titles ONLY (no bodies). Used sparingly.
    """
    if not robots_allows(url):
        raise PermissionError("robots-disallow")
    r = _http_get(url)
    if r.status_code in (403, 429):
        raise PermissionError(f"http-{r.status_code}")
    soup = BeautifulSoup(r.text, "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if len(text) < 25:  # skip nav/boilerplate; article titles are longer
            continue
        href = urljoin(url, a["href"])
        if _domain(href) != _domain(url):
            continue
        cu = f"{urlparse(href).scheme}://{urlparse(href).netloc}{urlparse(href).path}".rstrip("/")
        if cu in seen:
            continue
        seen.add(cu)
        out.append({"canonical_url": cu, "title": text[:200], "summary": "",
                    "published_at": None})
        if len(out) >= config.SETTINGS["max_items_per_feed"]:
            break
    return out


# ---------------------------------------------------------------------------
# The per-item pipeline + per-source fetch
# ---------------------------------------------------------------------------
def _retention_cutoff() -> str:
    """ISO timestamp: items published before this are outside the retention window."""
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(days=config.SETTINGS["retention_days"])).isoformat()


def process_item(repo: Repository, source: Source, item: dict) -> str:
    """
    Run one metadata item through: topic gate -> score -> angle tagging -> store.
    Returns one of: 'stored', 'gated', 'dup', 'old', 'skip'.
    """
    if not item.get("title") or not item.get("canonical_url"):
        return "skip"

    # Skip items already older than the retention window so the DB stays ~retention_days
    # and old archive posts don't churn back in between nightly prunes. Items with no
    # published date (e.g. scraped links) are treated as fresh and kept.
    pub = item.get("published_at")
    if pub and pub < _retention_cutoff():
        return "old"

    ev = topic.evaluate(item["title"], item["summary"])
    all_angles, is_critic = angle_mod.derive_angles(
        item["title"], item["summary"], source.angle,
        source_is_critic=(source.angle == config.CRITIC_ANGLE),
    )
    fingerprint = angle_mod.build_fingerprint(item["title"], item["summary"]) if ev["passed"] else []

    article = Article(
        id=None, canonical_url=item["canonical_url"], title=item["title"],
        summary=item["summary"], source_id=source.id, published_at=item["published_at"],
        score=ev["score"], passed_topic_gate=ev["passed"], primary_angle=source.angle,
        angles=all_angles, is_critic=is_critic, fingerprint=fingerprint,
    )
    inserted = repo.upsert_article(article)
    if not inserted:
        return "dup"
    return "stored" if ev["passed"] else "gated"


def fetch_source(repo: Repository, source: Source) -> dict:
    """
    Fetch one source end-to-end. Resolves a feed if needed, honors robots,
    marks status, and returns counters for logging.
    Never raises; records last_error on the source instead.
    """
    stats = {"source": source.name, "fetched": 0, "stored": 0, "gated": 0,
             "dup": 0, "old": 0, "status": source.status, "error": None}

    if source.status == "disabled":
        stats["status"] = "disabled"
        return stats

    try:
        # Resolve feed if we don't have one yet.
        feed_url = source.feed_url
        if not feed_url:
            feed_url, note = resolve_feed(source.url)
            if feed_url:
                source.feed_url = feed_url
                repo.update_source(source)

        items: List[dict] = []
        if feed_url:
            if not robots_allows(feed_url):
                raise PermissionError("robots-disallow")
            items = parse_feed_entries(feed_url)
        else:
            # No feed. Try a polite links-only scrape if robots allows; else no_feed.
            if robots_allows(source.url):
                try:
                    items = scrape_links(source.url)
                    if not items:
                        repo.set_source_status(source.id, "no_feed",
                                               "no feed found; scrape yielded nothing",
                                               touch_fetched=True)
                        stats["status"] = "no_feed"
                        return stats
                except PermissionError as pe:
                    repo.set_source_status(source.id, "blocked", str(pe), touch_fetched=True)
                    stats["status"] = "blocked"
                    stats["error"] = str(pe)
                    return stats
            else:
                repo.set_source_status(source.id, "blocked",
                                       "no feed and robots.txt disallows scraping",
                                       touch_fetched=True)
                stats["status"] = "blocked"
                return stats

        for item in items:
            stats["fetched"] += 1
            result = process_item(repo, source, item)
            if result in stats:
                stats[result] += 1

        repo.set_source_status(source.id, "active", None, touch_fetched=True)
        stats["status"] = "active"
    except PermissionError as pe:  # 403/429/robots
        repo.set_source_status(source.id, "blocked", str(pe), touch_fetched=True)
        stats["status"] = "blocked"
        stats["error"] = str(pe)
    except requests.RequestException as e:
        repo.set_source_status(source.id, "blocked", f"request error: {e}", touch_fetched=True)
        stats["status"] = "blocked"
        stats["error"] = str(e)
    except Exception as e:  # never silently drop a source
        log.exception("unexpected error fetching %s", source.name)
        repo.set_source_status(source.id, "blocked", f"error: {e}", touch_fetched=True)
        stats["status"] = "blocked"
        stats["error"] = str(e)
    return stats


def fetch_all(repo: Repository) -> dict:
    """Fetch every non-disabled source. Returns aggregate counters (for logging)."""
    agg = {"sources": 0, "fetched": 0, "stored": 0, "gated": 0, "dup": 0,
           "old": 0, "blocked": 0, "no_feed": 0}
    for source in repo.list_sources(include_disabled=False):
        s = fetch_source(repo, source)
        agg["sources"] += 1
        for k in ("fetched", "stored", "gated", "dup", "old"):
            agg[k] += s[k]
        if s["status"] == "blocked":
            agg["blocked"] += 1
        elif s["status"] == "no_feed":
            agg["no_feed"] += 1
        log.info("source=%-28s status=%-8s fetched=%d stored=%d topic-gated=%d dup=%d old=%d%s",
                 s["source"][:28], s["status"], s["fetched"], s["stored"], s["gated"],
                 s["dup"], s["old"], f" error={s['error']}" if s["error"] else "")
    log.info("FETCH DONE: sources=%d fetched=%d stored=%d topic-gated-out=%d dup=%d old=%d blocked=%d no_feed=%d",
             agg["sources"], agg["fetched"], agg["stored"], agg["gated"], agg["dup"],
             agg["old"], agg["blocked"], agg["no_feed"])
    return agg
