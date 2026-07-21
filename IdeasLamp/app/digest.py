"""
Daily topic digest — "what got posted on this day."

Summarizes a single day's gate-passed articles into an angle breakdown and the
most common keywords/entities (from each article's fingerprint). Used by the
nightly scheduler (logged) and by the /api/digest endpoint (shown in the UI).
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from .db import Repository


def today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def daily_digest(repo: Repository, date: Optional[str] = None, top_n: int = 12) -> dict:
    """Return a topic digest for `date` (YYYY-MM-DD, default today, UTC)."""
    date = date or today_str()
    articles = repo.list_articles(
        min_score=0.0, include_seen=True, only_gate_passed=True,
        date=date, limit=1000,
    )

    angle_counts: Counter = Counter()
    keyword_counts: Counter = Counter()
    critic_count = 0
    for a in articles:
        for ang in a.angles:
            angle_counts[ang] += 1
        if a.is_critic:
            critic_count += 1
        for kw in a.fingerprint:
            keyword_counts[kw] += 1

    return {
        "date": date,
        "total": len(articles),
        "critic_count": critic_count,
        "by_angle": angle_counts.most_common(),
        "top_keywords": keyword_counts.most_common(top_n),
        "sources": len({a.source_id for a in articles}),
    }


def format_digest_line(d: dict) -> str:
    """Compact one-line-ish summary for logging."""
    angles = ", ".join(f"{a}:{n}" for a, n in d["by_angle"][:8]) or "none"
    kws = ", ".join(f"{k}({n})" for k, n in d["top_keywords"][:8]) or "none"
    return (f"DIGEST {d['date']}: {d['total']} articles from {d['sources']} sources, "
            f"{d['critic_count']} critic | angles: {angles} | top topics: {kws}")
