"""
classify.py — the two-gate tech/AI filter + relevance score.

Mirrors the content-research aggregator's approach:
  Gate 1 (structural): is this a real outbound article link, or newsletter
      boilerplate (unsubscribe / view-in-browser / social)? Boilerplate is kept
      but flagged is_article=0 so it drops to the "other links" pile.
  Gate 2 (topical): does anchor_text + snippet match a tech/AI keyword as a
      WHOLE WORD? Broad = err toward inclusion.
  Score: summed weight of matched keywords, saturating-normalized to 0..1.

Whole-word matching is why "AI" won't fire on "email"/"again"/"detail" and
"tech" won't fire on "technically" mid-word... actually "tech" is its own token,
but it still won't match inside "biotechnology" because \b requires a boundary.
"""

import re
from urllib.parse import urlparse

import config

# Pre-compile one regex per keyword with word boundaries. For phrases we allow
# flexible whitespace between words. \b works on the ASCII word chars in our
# keywords (letters/digits/hyphens handled specially below).
_KEYWORD_PATTERNS = None


def _boundary_pattern(kw):
    # Escape, then allow flexible whitespace inside multi-word phrases.
    escaped = re.escape(kw)
    escaped = re.sub(r"\\\s+|\\ ", r"\\s+", escaped)  # spaces -> \s+
    # For keywords that end/start with a hyphen-joined form (e.g. "open-source",
    # "fine-tuning"), \b around the whole phrase is what we want.
    return re.compile(rf"(?<!\w){escaped}(?!\w)", re.IGNORECASE)


def _patterns():
    global _KEYWORD_PATTERNS
    if _KEYWORD_PATTERNS is None:
        _KEYWORD_PATTERNS = [
            (kw, weight, _boundary_pattern(kw))
            for kw, weight in config.KEYWORDS.items()
        ]
    return _KEYWORD_PATTERNS


_NEG_PATTERNS = None


def _neg_patterns():
    global _NEG_PATTERNS
    if _NEG_PATTERNS is None:
        _NEG_PATTERNS = [
            (kw, weight, _boundary_pattern(kw))
            for kw, weight in getattr(config, "NEGATIVE_KEYWORDS", {}).items()
        ]
    return _NEG_PATTERNS


def passes_gate1(url, anchor_text):
    """True if this looks like a real article link (not boilerplate)."""
    hay_text = (anchor_text or "").lower()
    hay_url = (url or "").lower()

    if hay_url.startswith("mailto:"):
        return False

    for marker in config.BOILERPLATE_MARKERS:
        if marker in hay_text:
            return False

    host = urlparse(url).netloc.lower()
    for h in config.BOILERPLATE_HOSTS:
        if h in host or h in hay_url:
            return False

    return True


def score_text(text):
    """Return {keyword: weight} for whole-word matches in `text`."""
    matched = {}
    for kw, weight, pat in _patterns():
        if pat.search(text or ""):
            matched[kw] = weight
    return matched


def _negative_penalty(text):
    """Return (matched_negatives, penalty_sum) for whole-word negative matches."""
    matched = []
    total = 0.0
    for kw, weight, pat in _neg_patterns():
        if pat.search(text or ""):
            matched.append(kw)
            total += weight
    return matched, total


def classify(url, anchor_text, snippet):
    """Two-gate classify with anchor-weighted scoring.

    Anchor keywords count at full weight; keywords found only in the surrounding
    snippet count at SNIPPET_WEIGHT_FACTOR (so a whole paragraph's AI-ness no
    longer makes every link in it score 1.00). Negative keywords subtract. A
    link whose anchor matched nothing is capped at SNIPPET_ONLY_SCORE_CAP so it
    can never outrank a link whose own headline is about AI.
    """
    is_article = passes_gate1(url, anchor_text)

    anchor_hits = score_text(anchor_text)
    snippet_hits = score_text(snippet)
    # snippet-only = matched in snippet but not already in the anchor
    snippet_only = {k: v for k, v in snippet_hits.items() if k not in anchor_hits}

    anchor_raw = sum(anchor_hits.values())
    snippet_raw = sum(snippet_only.values()) * config.SNIPPET_WEIGHT_FACTOR

    neg_matched, neg_pen = _negative_penalty(f"{anchor_text or ''} {snippet or ''}")
    raw = max(0.0, anchor_raw + snippet_raw - neg_pen)

    # Union of matched keywords, anchor terms first (most relevant), for chips.
    matched = list(anchor_hits.keys()) + list(snippet_only.keys())

    is_ai = bool(is_article and matched and raw > 0)
    if is_ai:
        score = min(1.0, raw / config.SCORE_SATURATION)
        if anchor_raw == 0:  # context-only link
            score = min(score, config.SNIPPET_ONLY_SCORE_CAP)
    else:
        score = 0.0

    return {
        "is_article": 1 if is_article else 0,
        "is_ai": 1 if is_ai else 0,
        "score": round(score, 4),
        "matched": matched,
        "matched_negative": neg_matched,
    }
