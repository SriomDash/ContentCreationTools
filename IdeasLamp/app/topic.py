"""
Topic gate (2 conditions) + relevance scoring (0..1).

This module applies the keyword sets from config.py; it contains NO keywords
of its own. Edit config.py to change behavior.
"""
from __future__ import annotations

import math
import re
from typing import List, Tuple

from . import config

# How hard the raw weighted score is squashed into 0..1.
# score = 1 - exp(-raw / SCORE_SATURATION). Larger => needs more matches to saturate.
SCORE_SATURATION = 8.0


def _compile(term: str) -> re.Pattern:
    """Word-boundary-ish, case-insensitive match. Handles phrases and punctuation."""
    # Escape, then allow the boundary to be non-word chars or string edges.
    esc = re.escape(term.lower())
    return re.compile(rf"(?<![a-z0-9]){esc}(?![a-z0-9])", re.IGNORECASE)


# Pre-compile all keyword patterns once at import for speed & determinism.
_AI_PATTERNS = [(k, _compile(k)) for k in config.AI_PRESENCE]
_DOMAIN_PATTERNS = [(k, _compile(k)) for k in config.DOMAINS]
_SCORING_PATTERNS = [(k, w, _compile(k)) for k, w in config.SCORING_KEYWORDS.items()]


def _matches(patterns, text: str) -> List[str]:
    return [k for k, pat in patterns if pat.search(text)]


def normalize_text(title: str, summary: str) -> str:
    """Combined text used for all keyword matching (title weighted implicitly by repetition)."""
    return f"{title} {title} {summary}".lower()  # title twice = mild title emphasis


def evaluate_gate1(text: str) -> Tuple[bool, List[str], List[str]]:
    """
    Gate 1: BOTH conditions required.
      A) AI presence  B) at least one domain
    Returns (passed, ai_hits, domain_hits).
    """
    ai_hits = _matches(_AI_PATTERNS, text)
    domain_hits = _matches(_DOMAIN_PATTERNS, text)
    passed = bool(ai_hits) and bool(domain_hits)
    return passed, ai_hits, domain_hits


def score_relevance(text: str) -> Tuple[float, List[str]]:
    """
    Gate 2: weighted keyword relevance squashed to 0..1.
    Returns (score, matched_scoring_keywords).
    """
    raw = 0.0
    matched: List[str] = []
    for k, w, pat in _SCORING_PATTERNS:
        if pat.search(text):
            raw += w
            matched.append(k)
    score = 1.0 - math.exp(-raw / SCORE_SATURATION)
    return round(score, 4), matched


def evaluate(title: str, summary: str):
    """
    Full topic evaluation for one item.
    Returns dict: passed, score, ai_hits, domain_hits, scoring_hits.
    Score is 0 for items that fail gate 1 (they won't show, but we store the reason).
    """
    text = normalize_text(title, summary)
    passed, ai_hits, domain_hits = evaluate_gate1(text)
    if not passed:
        return {"passed": False, "score": 0.0, "ai_hits": ai_hits,
                "domain_hits": domain_hits, "scoring_hits": []}
    score, scoring_hits = score_relevance(text)
    return {"passed": True, "score": score, "ai_hits": ai_hits,
            "domain_hits": domain_hits, "scoring_hits": scoring_hits}
