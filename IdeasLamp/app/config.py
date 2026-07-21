"""
============================================================================
 IdeasLamp — CONFIG (edit this file to tune behavior; no logic lives here)
============================================================================

This is the ONE place to edit the topic gate, scoring, and angle keywords.
Nothing in this file imports application logic, so you can freely change the
keyword sets and weights without touching how they are applied.

Overview of the pipeline this config drives:

    fetch -> TOPIC GATE (2 conditions) -> SCORE (0..1) -> ANGLE TAGGING -> store

Gate 1 (pass/fail, BOTH conditions required):
    A) AI_PRESENCE : the item must reference AI/ML/models/etc.
    B) DOMAINS     : the item must touch at least one human domain.
Gate 2 (0.0 - 1.0):
    SCORING_KEYWORDS : weighted relevance used for sort order + the slider.

Angle tagging:
    ANGLE_KEYWORDS   : per-angle keyword sets -> secondary angles.
    CRITIC_SIGNALS   : content signals that add the special "critic" tag.

Matching is case-insensitive, whole-word-ish (word-boundary) substring match.
Multi-word phrases (e.g. "large language model") are matched as phrases.
============================================================================
"""

# ---------------------------------------------------------------------------
# General settings
# ---------------------------------------------------------------------------
SETTINGS = {
    # Scheduler interval, in hours. Default 3h (spec).
    "fetch_interval_hours": 3.0,
    # Polite per-domain delay between HTTP requests, in seconds.
    "per_domain_delay_seconds": 2.0,
    # HTTP timeout, in seconds.
    "http_timeout_seconds": 15.0,
    # Honest, identifying User-Agent (NOT a spoofed browser). Edit contact if you like.
    "user_agent": "IdeasLampBot/1.0 (+personal AI content-research aggregator; contact: sriom@orderart.com.au)",
    # Max articles to keep per feed fetch (metadata only).
    "max_items_per_feed": 60,
    # Max length of stored summary/excerpt (characters). Metadata-only policy.
    "summary_max_chars": 500,
    # "Recent" window (days) used by the feed default view and pairing.
    "recent_days": 30,
    # Default min-relevance for the dashboard slider.
    "default_min_relevance": 0.2,
    # Candidate feed paths to try when a source URL is not itself a feed.
    "feed_probe_paths": ["/feed/", "/feed", "/rss", "/rss.xml", "/atom.xml", "/feed.xml", "/index.xml"],

    # --- Nightly jobs (see app/scheduler.py) ---
    # Hour of day (0-23, local server time) to run the nightly fetch + topic digest.
    "nightly_digest_hour": 2,
    "nightly_digest_minute": 0,
    # Hour of day to run the retention cleanup that deletes old articles.
    "retention_cleanup_hour": 3,
    "retention_cleanup_minute": 0,
    # Delete articles older than this many days (keeps the DB small automatically).
    # An article's age = its published date, or when we first stored it if no date.
    "retention_days": 10,
}

# ---------------------------------------------------------------------------
# GATE 1 — Condition A: AI PRESENCE
#   The item MUST reference AI/ML/models/etc. No AI presence -> item discarded.
#   (A pure climate / pure-psychology / pure-music piece with no AI angle fails.)
# ---------------------------------------------------------------------------
AI_PRESENCE = [
    "ai", "a.i.", "artificial intelligence", "machine learning", "ml",
    "deep learning", "neural network", "neural net", "llm", "large language model",
    "language model", "foundation model", "generative ai", "genai", "gen ai",
    "transformer", "diffusion model", "gpt", "chatgpt", "claude", "gemini",
    "llama", "mistral", "openai", "anthropic", "deepmind", "hugging face",
    "huggingface", "agentic", "ai agent", "autonomous agent", "rlhf",
    "fine-tune", "fine-tuning", "inference", "training run", "model weights",
    "reinforcement learning", "computer vision", "nlp", "natural language processing",
    "reasoning model", "multimodal", "embedding", "vector database", "rag",
    "alignment", "superintelligence", "agi", "chatbot", "copilot", "stable diffusion",
    "midjourney", "text-to-image", "text-to-video", "prompt", "prompting",
]

# ---------------------------------------------------------------------------
# GATE 1 — Condition B: DOMAINS
#   The item must touch at least one human domain. In practice B is almost
#   always satisfied once A is; its purpose is to let you EXCLUDE pure-hype
#   items with no substantive domain hook (tighten this set to be stricter).
# ---------------------------------------------------------------------------
DOMAINS = [
    # tech
    "software", "hardware", "chip", "gpu", "compute", "benchmark", "architecture",
    "engineering", "developer", "code", "programming", "infrastructure", "cloud",
    # biology / science
    "biology", "protein", "genome", "gene", "dna", "rna", "cell", "neuroscience",
    "brain", "drug", "molecule", "disease", "medicine", "clinical", "health",
    "evolution", "organism", "microbiome", "fold", "folding",
    # philosophy
    "philosophy", "consciousness", "mind", "ethics", "morality", "agency",
    "meaning", "epistemology", "metaphysics", "free will", "reason", "truth",
    # psychology
    "psychology", "cognition", "attention", "behavior", "behaviour", "emotion",
    "wellbeing", "well-being", "mental health", "relationship", "memory", "learning",
    # climate / energy
    "climate", "emissions", "carbon", "energy", "grid", "water", "sustainability",
    "renewable", "power", "electricity", "data center", "data centre", "environment",
    # culture / society / labor / creation
    "culture", "art", "music", "film", "creator", "creative", "media", "society",
    "politics", "policy", "law", "copyright", "deepfake", "labor", "labour", "jobs",
    "work", "economy", "education", "content", "journalism", "history", "religion",
    # market
    "market", "startup", "company", "business", "funding", "investment", "revenue",
    "acquisition", "ipo", "valuation", "industry", "product",
]

# ---------------------------------------------------------------------------
# GATE 2 — SCORING (weighted keyword relevance -> 0.0 .. 1.0)
#   Higher weight = stronger relevance signal for THIS channel (AI-as-a-lens).
#   The raw weighted sum is squashed into 0..1 (see topic.py SCORE_SATURATION).
#   Add/remove terms and tune weights freely; the logic reads this verbatim.
# ---------------------------------------------------------------------------
SCORING_KEYWORDS = {
    # Collision / "big idea" terms — the heart of the channel. Weighted high.
    "emergence": 3.0, "reasoning": 3.0, "consciousness": 3.0, "intelligence": 3.0,
    "agency": 2.5, "alignment": 2.5, "understanding": 2.0, "cognition": 2.5,
    "creativity": 2.0, "meaning": 2.0, "mind": 2.0, "sentience": 3.0,
    "interpretability": 2.5, "world model": 2.5, "self-improvement": 2.5,
    # Substantive AI research signals.
    "breakthrough": 1.5, "capabilities": 1.5, "benchmark": 1.2, "scaling": 1.5,
    "generalization": 1.8, "protein": 1.8, "genome": 1.5, "neuroscience": 2.0,
    "brain": 1.8, "drug discovery": 1.8, "fold": 1.2,
    # Critique / stakes signals (pairs well with critic pairing).
    "risk": 1.2, "harm": 1.5, "bias": 1.5, "hype": 1.2, "bubble": 1.2,
    "regulation": 1.0, "safety": 1.5, "ethics": 1.8,
    # Human-impact signals.
    "creator": 1.2, "artist": 1.2, "labor": 1.2, "jobs": 1.2, "society": 1.2,
    "philosophy": 1.5, "psychology": 1.5, "climate": 1.2, "energy": 1.2,
    # Lower-weight but on-topic.
    "model": 0.8, "training": 0.8, "gpu": 0.6, "compute": 0.8, "agent": 1.0,
    "open source": 1.0, "multimodal": 1.0, "research": 0.6,
}

# ---------------------------------------------------------------------------
# ANGLE KEYWORDS — derive SECONDARY angles from content.
#   The PRIMARY angle always comes from the source (sources.csv).
#   Any angle whose keywords appear is added as a secondary angle.
#   "market" and "tech" are also angles; "critic" is handled separately below.
# ---------------------------------------------------------------------------
ANGLE_KEYWORDS = {
    "biology": [
        "protein", "genome", "gene", "dna", "rna", "neuroscience", "cell", "drug",
        "fold", "folding", "molecule", "disease", "clinical", "biology", "organism",
        "microbiome", "enzyme", "alphafold", "brain", "cancer", "vaccine", "medicine",
    ],
    "philosophy": [
        "consciousness", "mind", "ethics", "agency", "meaning", "alignment",
        "epistemology", "metaphysics", "free will", "morality", "sentience",
        "philosophy", "existential", "truth", "reason", "phenomenology",
    ],
    "psychology": [
        "attention", "behavior", "behaviour", "relationship", "wellbeing",
        "well-being", "cognition", "emotion", "mental health", "memory",
        "psychology", "loneliness", "motivation", "perception", "habit",
    ],
    "climate": [
        "emissions", "energy", "compute cost", "water", "grid", "sustainability",
        "carbon", "renewable", "power", "electricity", "data center", "data centre",
        "climate", "environment", "footprint",
    ],
    "culture": [
        "art", "music", "film", "creator", "deepfake", "copyright", "society",
        "culture", "media", "artist", "creative", "journalism", "meme", "aesthetic",
        "writing", "literature", "photography", "design",
    ],
    "tech": [
        "model", "benchmark", "gpu", "architecture", "inference", "training",
        "compute", "open source", "framework", "api", "chip", "cluster",
        "latency", "throughput", "quantization", "fine-tune", "pipeline",
    ],
    "market": [
        "funding", "revenue", "acquisition", "ipo", "valuation", "startup",
        "investment", "raise", "series a", "series b", "billion", "market cap",
        "customers", "enterprise", "pricing", "layoffs", "profit",
    ],
}

# ---------------------------------------------------------------------------
# CRITIC SIGNALS — content that marks a dissenting / skeptical take on AI.
#   Applied IN ADDITION to any source flagged "critic" in sources.csv.
#   A critic article ALSO keeps its domain angle(s).
# ---------------------------------------------------------------------------
CRITIC_SIGNALS = [
    "skeptic", "skeptical", "sceptic", "overhyped", "hype", "debunk", "debunked",
    "harm", "harmful", "misleading", "ai can't", "ai cannot", "can't actually",
    "bubble", "snake oil", "grift", "myth", "overrated", "backlash", "false promise",
    "doesn't work", "failure", "flawed", "exaggerated", "not intelligent",
    "stochastic parrot", "slop", "enshittification", "scam",
]

# The full set of angles used by the UI chips (order matters for display).
ALL_ANGLES = ["tech", "biology", "philosophy", "psychology", "climate", "culture", "market"]
CRITIC_ANGLE = "critic"

# Substrings in a source's `notes` that flag it as paywalled (metadata-only, never scrape body).
PAYWALL_FLAGS = ["paywall"]
