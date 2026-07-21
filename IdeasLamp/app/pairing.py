"""
Cross-angle pairing — the channel's key differentiator.

Deterministic + explainable (no LLM in v1). Structured so an LLM scorer can be
dropped into `_overlap_score` / candidate ranking later without touching callers.

Two modes:
  * "cross"  : two above-threshold recent articles with DIFFERENT primary angles
               that share the most keywords/entities.
  * "critic" : a positive/announcement article paired with a recent critic-tagged
               article sharing keywords/entities (lab launch vs skeptic's takedown).

Re-roll: pairs are ranked deterministically; `offset` walks down the ranking.
Lock: fix one article (by id) and rank partners against it.
"""
from __future__ import annotations

from typing import List, Optional

from . import config
from .db import Repository
from .models import Article


def _overlap(a: Article, b: Article) -> List[str]:
    """Shared fingerprint terms — the explainable 'why' of a pairing."""
    return sorted(set(a.fingerprint) & set(b.fingerprint))


def _overlap_score(a: Article, b: Article, shared: List[str]) -> float:
    """
    Heuristic strength of a pairing. Deterministic. Swap this for an LLM/embedding
    scorer later — callers only depend on 'higher is better'.
    """
    if not shared:
        return 0.0
    # Reward shared-term count, then combined relevance as a tiebreaker.
    return len(shared) * 10.0 + (a.score + b.score)


def _candidates(repo: Repository, recent_days: int, min_score: float) -> List[Article]:
    arts = repo.list_articles(
        min_score=min_score, include_seen=False, only_gate_passed=True,
        recent_days=recent_days, limit=500,
    )
    # Only articles with a usable fingerprint can be paired.
    return [a for a in arts if a.fingerprint]


def _rank_pairs(candidates: List[Article], mode: str,
                locked: Optional[Article]) -> List[dict]:
    """Return all valid pairs ranked by (overlap_score desc, ids) — fully deterministic."""
    pairs = []
    n = len(candidates)
    for i in range(n):
        a = candidates[i]
        for j in range(i + 1, n):
            b = candidates[j]

            if mode == "cross":
                if a.primary_angle == b.primary_angle:
                    continue
            elif mode == "critic":
                # exactly one side is a critic piece.
                if a.is_critic == b.is_critic:
                    continue

            shared = _overlap(a, b)
            if not shared:
                continue
            score = _overlap_score(a, b, shared)

            # Orient the pair for display: in critic mode, non-critic first.
            left, right = a, b
            if mode == "critic" and left.is_critic and not right.is_critic:
                left, right = right, left

            pairs.append({"left": left, "right": right, "shared": shared, "strength": score})

    # If an article is locked, keep only pairs that include it.
    if locked is not None:
        pairs = [p for p in pairs
                 if p["left"].id == locked.id or p["right"].id == locked.id]
        # Ensure locked article is on the left for stable display.
        for p in pairs:
            if p["right"].id == locked.id:
                p["left"], p["right"] = p["right"], p["left"]

    # Deterministic ordering: strength desc, then stable id ordering.
    pairs.sort(key=lambda p: (-p["strength"], p["left"].id or 0, p["right"].id or 0))
    return pairs


def _explain(pair: dict, mode: str) -> str:
    left, right, shared = pair["left"], pair["right"], pair["shared"]
    terms = ", ".join(shared[:6])
    if mode == "critic":
        return (f"Announcement/analysis ({left.primary_angle}) vs a critic take - "
                f"both touch: {terms}. Build the reel as claim -> pushback.")
    return (f"Different angles ({left.primary_angle} × {right.primary_angle}) that "
            f"collide on: {terms}. Read one through the other's lens.")


def _serialize(article: Article) -> dict:
    return {
        "id": article.id, "title": article.title, "summary": article.summary,
        "url": article.canonical_url, "source": article.source_name,
        "primary_angle": article.primary_angle, "angles": article.angles,
        "is_critic": article.is_critic, "score": article.score,
        "published_at": article.published_at, "fingerprint": article.fingerprint,
    }


def find_pairing(repo: Repository, mode: str = "cross", offset: int = 0,
                 lock_id: Optional[int] = None,
                 recent_days: Optional[int] = None,
                 min_score: Optional[float] = None) -> Optional[dict]:
    """
    Return a single pairing (the offset-th best), or None if none exist.
    mode: 'cross' | 'critic'. offset: re-roll counter. lock_id: fix one article.
    """
    recent_days = recent_days if recent_days is not None else config.SETTINGS["recent_days"]
    min_score = min_score if min_score is not None else config.SETTINGS["default_min_relevance"]

    candidates = _candidates(repo, recent_days, min_score)
    locked = repo.get_article(lock_id) if lock_id else None
    if lock_id and (locked is None or not locked.fingerprint):
        return None
    # Make sure the locked article is in the candidate pool.
    if locked and locked.id not in {c.id for c in candidates}:
        candidates.append(locked)

    pairs = _rank_pairs(candidates, mode, locked)
    if not pairs:
        return None

    total = len(pairs)
    pair = pairs[offset % total]  # wrap-around re-roll
    return {
        "mode": mode,
        "offset": offset % total,
        "total_pairs": total,
        "left": _serialize(pair["left"]),
        "right": _serialize(pair["right"]),
        "shared_terms": pair["shared"],
        "strength": round(pair["strength"], 3),
        "why": _explain(pair, mode),
    }
