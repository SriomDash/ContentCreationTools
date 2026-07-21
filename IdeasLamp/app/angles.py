"""
Angle tagging + critic detection + pairing fingerprint.

Applies ANGLE_KEYWORDS / CRITIC_SIGNALS from config.py. No keywords here.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from . import config
from .topic import _compile  # reuse the same word-boundary matcher

_ANGLE_PATTERNS = {
    angle: [(k, _compile(k)) for k in kws]
    for angle, kws in config.ANGLE_KEYWORDS.items()
}
_CRITIC_PATTERNS = [(k, _compile(k)) for k in config.CRITIC_SIGNALS]

# Fingerprint vocabulary for pairing = every meaningful keyword we know about.
# Overlap on these is what makes a pairing explainable.
_FINGERPRINT_VOCAB = sorted(set(
    list(config.SCORING_KEYWORDS.keys())
    + [k for kws in config.ANGLE_KEYWORDS.values() for k in kws]
    + config.AI_PRESENCE
))
_FINGERPRINT_PATTERNS = [(k, _compile(k)) for k in _FINGERPRINT_VOCAB]

# Generic AI terms too common to be useful as a pairing "shared entity".
_FINGERPRINT_STOPWORDS = {"ai", "a.i.", "ml", "model", "models", "research"}


def derive_angles(title: str, summary: str, primary_angle: str,
                  source_is_critic: bool) -> Tuple[List[str], bool]:
    """
    Returns (all_angles, is_critic).
    all_angles = [primary] + any secondary angles matched by content (deduped, primary first).
    is_critic = source flagged critic OR content critic signal present.
    """
    text = f"{title} {title} {summary}".lower()

    matched = []
    for angle, patterns in _ANGLE_PATTERNS.items():
        if any(pat.search(text) for _, pat in patterns):
            matched.append(angle)

    # Primary always first; keep order stable and unique.
    ordered: List[str] = [primary_angle] if primary_angle in (config.ALL_ANGLES) else []
    if primary_angle not in config.ALL_ANGLES and primary_angle != config.CRITIC_ANGLE:
        # e.g. an odd source angle; still record it as primary.
        ordered = [primary_angle]
    for a in matched:
        if a not in ordered:
            ordered.append(a)
    if not ordered:
        ordered = [primary_angle]

    is_critic = source_is_critic or any(pat.search(text) for _, pat in _CRITIC_PATTERNS)
    return ordered, is_critic


def build_fingerprint(title: str, summary: str) -> List[str]:
    """Deterministic keyword/entity set for pairing overlap."""
    text = f"{title} {summary}".lower()
    fp = [k for k, pat in _FINGERPRINT_PATTERNS
          if pat.search(text) and k not in _FINGERPRINT_STOPWORDS]
    # Add simple proper-noun-ish entities from the title (Capitalized multi-letter tokens),
    # which catches lab/product/person names the keyword vocab may miss.
    for tok in re.findall(r"\b([A-Z][A-Za-z0-9]{2,})\b", title):
        low = tok.lower()
        if low not in _FINGERPRINT_STOPWORDS and low not in fp:
            fp.append(low)
    return sorted(set(fp))
