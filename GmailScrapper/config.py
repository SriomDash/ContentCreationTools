"""
config.py — the ONE editable block for this tool.

Everything you'd normally want to tweak lives here:
  * which Gmail label to scan
  * how far back each run looks
  * the tech/AI keyword set + weights (drives both the flag and the score)
  * the two-gate filter rules

This is the companion config to your content-research aggregator. It mirrors the
same "two-gate filter + weighted keyword overlap" approach so the two tools stay
consistent. If you later share the aggregator's real config, port the keyword
weights straight into KEYWORDS below.

NOTE: This app is strictly READ-ONLY on Gmail (gmail.readonly scope only).
Nothing here can change that; the scope is asserted at runtime in auth.py.
"""

# ---------------------------------------------------------------------------
# 1. What to scan
# ---------------------------------------------------------------------------

# The single Gmail label whose newsletters get scanned. The app NEVER reads
# outside this label. If the label isn't found, ingest.py prints your available
# labels so you can copy the exact name here.
LABEL = "AI-News"

# Rolling window: each run pulls messages received in the last N days.
SINCE_DAYS = 2

# ---------------------------------------------------------------------------
# 2. Two-gate filter
# ---------------------------------------------------------------------------
# GATE 1 (structural): is this a real outbound article link at all, or is it
#   newsletter boilerplate? Boilerplate links are still stored (nothing is
#   discarded) but flagged is_article=0 so they stay out of the way.
# GATE 2 (topical): does the link look tech/AI? Handled by KEYWORDS below.

# Anchor text or URL containing any of these (case-insensitive substring) is
# treated as non-article boilerplate (Gate 1 = fail). Broad on purpose; these
# are the usual newsletter chrome.
BOILERPLATE_MARKERS = [
    "unsubscribe", "manage preferences", "manage your subscription",
    "update your preferences", "view in browser", "view this email",
    "view online", "read online", "privacy policy", "terms of service",
    "advertise", "sponsor this", "forward to a friend", "add us to your",
    "follow us", "share this", "tweet", "share on", "become a member",
    "upgrade to paid", "manage subscription", "email preferences",
    "why am i seeing this", "report spam",
]

# URL hosts that are almost always social / share / mail infrastructure, not the
# article itself (Gate 1 = fail). Substring match on the host.
BOILERPLATE_HOSTS = [
    "twitter.com", "x.com", "facebook.com", "instagram.com", "linkedin.com",
    "youtube.com/channel", "threads.net", "t.me", "whatsapp.com",
    "mailto:", "list-manage.com/unsubscribe", "sparkloop.com",
]

# ---------------------------------------------------------------------------
# 3. Tech/AI keyword set + weights  (Gate 2 + relevance score)
# ---------------------------------------------------------------------------
# BROAD match: err toward inclusion. Each keyword is matched as a WHOLE WORD
# (word boundaries) against anchor_text + surrounding snippet, case-insensitive.
# So "AI" will NOT fire inside "email", "again", or "detail"; "tech" is
# whole-word only.
#
# The weight is the keyword's contribution to the relevance score. Higher =
# stronger tech/AI signal. A link is flagged is_ai=1 if it matches >= 1 keyword
# (Gate 2 pass). The 0..1 score is the summed weight of matched keywords, run
# through a saturating normalizer (see classify.py) so a few strong hits or many
# weak ones both land sensibly in [0,1].
#
# Multi-word keywords (e.g. "machine learning") are matched as a whole phrase.
# Add/remove/retune freely — this is the knob you'll touch most.

KEYWORDS = {
    # --- core AI (strong signal) ---
    "ai": 1.0,
    "artificial intelligence": 1.0,
    "agi": 1.0,
    "machine learning": 1.0,
    "ml": 0.7,
    "deep learning": 1.0,
    "neural network": 0.9,
    "llm": 1.0,
    "large language model": 1.0,
    "generative ai": 1.0,
    "genai": 1.0,
    "gpt": 0.9,
    "chatgpt": 0.9,
    "claude": 0.9,
    "gemini": 0.8,
    "llama": 0.7,
    "mistral": 0.7,
    "transformer": 0.7,
    "diffusion": 0.7,
    "prompt": 0.5,
    "prompting": 0.5,
    "fine-tuning": 0.7,
    "fine tuning": 0.7,
    "rag": 0.7,
    "embeddings": 0.7,
    "inference": 0.6,
    "training": 0.5,
    "model": 0.4,
    "models": 0.4,
    "agent": 0.7,
    "agents": 0.7,
    "agentic": 0.8,
    "multimodal": 0.7,
    "open source": 0.4,
    "open-source": 0.4,
    "benchmark": 0.5,
    "hallucination": 0.6,
    "alignment": 0.5,
    "reasoning": 0.5,

    # --- AI companies / labs (strong signal) ---
    "openai": 1.0,
    "anthropic": 1.0,
    "deepmind": 1.0,
    "google deepmind": 1.0,
    "hugging face": 0.8,
    "huggingface": 0.8,
    "nvidia": 0.7,
    "stability ai": 0.8,
    "cohere": 0.7,
    "perplexity": 0.7,
    "midjourney": 0.7,

    # --- broader tech (medium signal) ---
    "tech": 0.5,
    "technology": 0.5,
    "software": 0.5,
    "startup": 0.5,
    "startups": 0.5,
    "developer": 0.5,
    "developers": 0.5,
    "engineering": 0.4,
    "programming": 0.5,
    "coding": 0.5,
    "code": 0.4,
    "api": 0.5,
    "cloud": 0.4,
    "data": 0.3,
    "dataset": 0.5,
    "gpu": 0.6,
    "chip": 0.5,
    "chips": 0.5,
    "semiconductor": 0.6,
    "robotics": 0.6,
    "robot": 0.5,
    "automation": 0.5,
    "cybersecurity": 0.5,
    "security": 0.3,
    "quantum": 0.6,
    "silicon valley": 0.5,
    "saas": 0.5,
    "infrastructure": 0.3,
    "compute": 0.5,
    "python": 0.5,
    "database": 0.4,
    "framework": 0.3,
}

# Score normalizer: the summed weight of matched keywords is divided by this and
# capped at 1.0. Lower => scores saturate faster (easier to hit high relevance).
# Tune to taste; 2.0 means "~two strong keywords => full score".
SCORE_SATURATION = 2.0

# --- anchor vs snippet weighting ---------------------------------------------
# A keyword found in the link's own ANCHOR TEXT is a much stronger signal that
# THIS link is about tech/AI than one found only in the surrounding paragraph
# (where every link in the paragraph would otherwise inherit the same score).
# Keywords matched only in the snippet contribute at this reduced factor.
SNIPPET_WEIGHT_FACTOR = 0.35

# Hard cap on the score of a link whose anchor text matched NO keyword (its
# signal comes purely from surrounding context). Keeps context-only links in
# play (broad inclusion) but stops them from ever outranking a link whose own
# headline is about AI. Set to 1.0 to disable the cap.
SNIPPET_ONLY_SCORE_CAP = 0.5

# --- negative keywords -------------------------------------------------------
# Whole-word matches here subtract from the raw score (floored at 0). Use for
# promo / noise contexts that shouldn't count as a tech/AI article. If negatives
# cancel out the positives, the link is no longer flagged tech/AI. Broad filter,
# tune freely.
NEGATIVE_KEYWORDS = {
    "webinar": 0.8,
    "sponsored": 0.8,
    "sponsor": 0.6,
    "advertisement": 1.0,
    "discount": 0.8,
    "coupon": 1.0,
    "promo code": 1.0,
    "sale": 0.5,
    "% off": 1.0,
    "hiring": 0.6,
    "job board": 1.0,
    "apply now": 0.8,
    "register now": 0.6,
    "buy now": 0.8,
    "gift": 0.5,
    "giveaway": 0.8,
}

# ---------------------------------------------------------------------------
# 4. Storage / server
# ---------------------------------------------------------------------------
DB_PATH = "digest.db"
HOST = "127.0.0.1"
PORT = 8000
