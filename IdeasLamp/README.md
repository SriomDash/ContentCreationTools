# IdeasLamp

A personal, self-hosted content-research aggregator for a short-form AI video
(reels) workflow. It pulls from a list of sources you maintain, keeps **only
AI-as-a-lens-on-a-human-domain** content, scores each item for relevance, tags
it by **angle**, shows everything in one feed, and — the point of the whole
thing — suggests **cross-angle article pairings** to spark unique reel ideas.

The differentiator isn't news; it's the *collision* between angles: an AI-biology
result read through a philosophy lens, a dry benchmark read through "what does
this mean for intelligence," a lab's launch paired with a skeptic's takedown.

---

## Run it (one command)

```bash
pip install -r requirements.txt
python run.py
```

Then open <http://127.0.0.1:8000>.

On first start the app:
1. creates the SQLite DB at `data/app.db`,
2. seeds every row from `sources.csv`,
3. starts the background scheduler (three jobs — see **Scheduler** below),
4. kicks off one immediate fetch so the feed fills within a minute or two.

Optional environment overrides: `IDEASLAMP_HOST` (default `127.0.0.1`),
`IDEASLAMP_PORT` (default `8000`).

---

## The two-gate topic filter (the hard requirement)

The channel thesis is "AI as a lens on everything human," so the gate is **not**
"is this tech." An item must clear **Gate 1** (pass/fail) before it is scored.

**Gate 1 — both conditions required:**
- **Condition A — AI presence.** The item must reference AI/ML/models/etc.
  (keyword set `AI_PRESENCE`). *No AI presence → discarded.* A pure-climate,
  pure-psychology, or pure-music piece with no AI angle fails here.
- **Condition B — domain.** The item must touch at least one human domain — tech,
  biology, philosophy, psychology, climate, culture, music, art, society, labor,
  content-creation, market, etc. (keyword set `DOMAINS`). In practice B is almost
  always satisfied once A is; its purpose is to let you *exclude pure-hype items
  with no substantive domain hook* by tightening `DOMAINS`.

**Gate 2 — relevance score (0.0–1.0).** Only Gate-1 passers are scored, using the
weighted keyword set `SCORING_KEYWORDS`. The raw weighted sum is squashed into
0–1 (`1 - exp(-raw / SCORE_SATURATION)`). This score drives the feed sort order
and the min-relevance slider.

Items that fail Gate 1 are still stored (with `passed_topic_gate = 0`, score 0)
so counts are honest and nothing is silently lost — they just never appear in the
feed.

### Where to edit the gates, scoring, and angle keywords

**Everything tunable lives in [`app/config.py`](app/config.py)** — one commented
file, no logic. Edit these and restart:

| What | Constant in `app/config.py` |
|------|------------------------------|
| AI-presence set (Condition A) | `AI_PRESENCE` |
| Domain set (Condition B) | `DOMAINS` |
| Weighted scoring keywords (Gate 2) | `SCORING_KEYWORDS` |
| Per-angle keyword sets (secondary angles) | `ANGLE_KEYWORDS` |
| Critic content signals | `CRITIC_SIGNALS` |
| Fetch interval, rate limit, User-Agent, summary length, "recent" window, feed-probe paths | `SETTINGS` |
| Nightly digest time, retention cleanup time, **retention days (default 10)** | `SETTINGS` |
| How hard scores saturate to 1.0 | `SCORE_SATURATION` in [`app/topic.py`](app/topic.py) |

Matching is case-insensitive with word boundaries; multi-word entries (e.g.
`"large language model"`) match as phrases.

---

## Angle tagging

- **Primary angle** always comes from the source (`angle` column in `sources.csv`,
  or the dropdown when you add a source).
- **Secondary angles** are derived from content via `ANGLE_KEYWORDS`. An article
  stores its primary angle plus every secondary angle it matches.
- Angles: `tech, biology, philosophy, psychology, climate, culture, market` —
  plus the special **`critic`** tag.

### Critic tag

`critic` marks a dissenting/skeptical take on AI. It is applied when **either**:
- the source is tagged `critic` in `sources.csv` (e.g. Gary Marcus, DAIR, Ed
  Zitron), **or**
- the content matches a `CRITIC_SIGNALS` term (`skeptic, overhyped, debunk, harm,
  misleading, "ai can't", bubble, ...`).

A critic article **keeps its domain angle(s)** too, and the `CRITIC` tag is shown
prominently (red pill + left border on the card) so you can spot dissent at a
glance. There's a distinct **critic** filter chip.

---

## Cross-angle pairing (the key feature)

Click **Find me a pairing**. Two modes:

- **Cross-angle** — picks a high-relevance recent article, then the recent article
  with the **highest keyword/entity overlap whose primary angle differs**. Shown
  side by side with the shared terms highlighted.
- **Critic pairing** — pairs a positive/announcement article with a recent
  **critic-tagged** article sharing keywords/entities (lab launch vs skeptic's
  takedown). Non-critic article on the left, critic on the right.

Controls:
- **Re-roll** walks deterministically down the ranked list of candidate pairs
  (wraps around at the end).
- **Lock this one** fixes an article and pairs everything against it.
- Every pairing shows **why** it was chosen (the shared terms + a one-line reel
  suggestion) and its rank (`Pairing 3 of 128`).

It's fully **deterministic and explainable** — no LLM in v1. The scoring lives in
`_overlap_score` in [`app/pairing.py`](app/pairing.py); swap that (and the
candidate ranking) for an embedding/LLM scorer later without touching any caller.
The "shared terms" come from each article's stored `fingerprint` (matched
keywords + capitalized entities from the title).

---

## Sources & add-source

- **Feed resolution:** for each source we try, in order: (1) is the URL itself a
  feed? (2) `<link rel="alternate" type="application/rss+xml">` in the page HTML,
  (3) common paths (`/feed/`, `/rss`, `/atom.xml`, `/feed.xml`, `/index.xml`, …).
  Every probe honors robots.txt.
- **No feed + robots allows** → a minimal polite scrape for **links + titles
  only** (never bodies). **No feed + robots disallows** → status `no_feed`/`blocked`.
- **Add a source** any time from the **Sources** drawer (URL + angle). It resolves
  the feed, checks robots, fetches immediately in the background, and shows status
  `active` / `blocked` / `no_feed`.
- **Remove / disable / re-fetch** each source from the same drawer. Sources are
  persisted in the DB.
- Articles are **deduped by canonical URL**.

---

## Compliance: robots.txt, rate limits, and the metadata-only / links-out policy

These are enforced in [`app/ingest.py`](app/ingest.py):

- **Metadata only.** We store *only* title, a short summary/excerpt (capped at
  `summary_max_chars`), source, published date, and the canonical link. We
  **never** fetch, store, or display article bodies or full-page HTML — not for
  paywalled items, not for anyone. The dashboard **links out** to the original
  (opens in a new tab). Rows flagged `PAYWALL` in `sources.csv` are marked
  `is_paywall` and shown with a **PAYWALL** badge; we still only ever take feed
  metadata for them and never attempt to scrape a body or bypass a paywall.
- **robots.txt** is checked before *every* fetch (feed or scrape). Disallowed →
  we do not fetch and the source is marked `blocked` with the reason shown.
  (Example: SEP / plato.stanford.edu disallows `/rss/` and `/`, so it correctly
  shows as blocked even though a feed URL was listed.)
- **Honest User-Agent** (`IdeasLampBot/1.0 …`, editable in `SETTINGS`). No browser
  spoofing.
- **Per-domain rate limiting** (`per_domain_delay_seconds`, default 2s) and
  **feeds preferred over scraping**.
- **On block / 403 / 429 / robots-disallow / error →** the source is marked
  `blocked` (or `no_feed`) and **shown on the dashboard with its error** — never
  silently dropped.

### Logging

Each fetch logs per-source and aggregate counters:
```
source=arxiv.org   status=active fetched=60 stored=33 topic-gated=27 dup=0
FETCH DONE: sources=66 fetched=997 stored=... topic-gated-out=... dup=... blocked=4 no_feed=1
```

---

## Dashboard

One feed, sorted by relevance then recency. Each **card**: score badge, title
(click-through to original in a new tab), source, published time, angle tag(s)
with the critic tag surfaced prominently, and a **Dismiss** control (dismissed
items leave the feed; "Show dismissed" brings them back).

Controls: **search box** (keyword, see below), **★ Saved** toggle, **min-relevance
slider** (default 0.2, live), **date filter** (see below), **angle filter chips**
(all / tech / biology / philosophy / psychology / climate / culture / market + a
distinct **critic** chip), **Find a pairing**, **Fetch**, and the **Sources** drawer.

### Search (keyword, no LLM)

The search box filters the feed by keyword — each whitespace-separated word must
appear (AND) in an article's title or summary, case-insensitive. Purely keyword
based (SQL `LIKE`); no LLM, no cost, instant.

### Star / saved articles

Every card has a **☆ star**. Click it to save the article for reference. Saved
articles are **exempt from the 10-day retention prune — they are never
auto-deleted** (only removed when you un-star them). Click **★ Saved** in the
toolbar to view your saved library, which shows every starred item regardless of
age or whether it was dismissed.

### Date filter + daily topic digest

Pick a **Day** (the date box autocompletes to days that actually have articles;
**Today** and **Clear** buttons are next to it) to see everything posted that
day. When a day is selected, a **digest strip** appears above the feed
summarizing that day's topics: article/source/critic counts, the **angle
breakdown** (tech 126, philosophy 11, …), and the **top keywords/entities**
(llm ·29, reasoning ·11, …). This is the same digest the nightly job logs.

## Scheduler

Three background jobs run automatically (all configurable in `SETTINGS`):

1. **Interval fetch** — every `fetch_interval_hours` (default **3h**). Keeps the
   feed fresh through the day.
2. **Nightly digest** — once a night at `nightly_digest_hour:minute` (default
   **02:00**, server local time). Runs a fetch, then computes and **logs the
   day's topic digest** (angles + top keywords). View any day's digest in the UI
   date strip or via `GET /api/digest?date=YYYY-MM-DD`.
3. **Retention cleanup** — once a day at `retention_cleanup_hour:minute` (default
   **03:00**). **Deletes articles older than `retention_days` (default 10)** so
   the DB stays small without any manual pruning. An article's age is its
   published date (or, if it has none, when it was first stored). You can trigger
   it manually any time with `POST /api/prune`.

**Ingestion also enforces the window:** items whose published date is already
older than `retention_days` are skipped at fetch time (never stored). This keeps
the DB to ~10 days and stops old archive posts (essay/blog feeds often republish
their full history with original dates) from churning back in between prunes.
Items with no published date are treated as fresh and kept.

**Starred articles are never auto-deleted.** Both the prune and (implicitly) the
saved library keep starred items forever, regardless of age — they're your
permanent reference shelf. Un-star an item to let it fall out of the window.

---

## Data model

**`sources`**: `id, url, feed_url, name, angle, type, notes, is_paywall, status
(active|blocked|no_feed|disabled), last_fetched, last_error`

**`articles`**: `id, canonical_url (UNIQUE), title, summary, source_id,
published_at, score, passed_topic_gate, primary_angle, angles (JSON),
is_critic, fingerprint (JSON), seen, created_at`

Schema DDL: [`app/schema.sql`](app/schema.sql).

### Storage is isolated (SQLite now, Postgres later)

All SQL lives behind the `Repository` interface in [`app/db.py`](app/db.py).
Application code depends only on `Repository` + the dataclasses in
[`app/models.py`](app/models.py) — never on `sqlite3` directly. To move to
Postgres, add a `PostgresRepository(Repository)` and change the one line in
`get_repository()`; no caller changes.

---

## Project layout

```
app/
  config.py     ← ALL editable keyword sets + settings (edit this)
  db.py         ← Repository interface + SQLite implementation (all SQL here)
  models.py     ← Source / Article dataclasses
  schema.sql    ← DDL
  topic.py      ← two-gate filter + 0..1 scoring
  angles.py     ← primary/secondary angle tagging, critic detection, fingerprints
  ingest.py     ← feed resolution, robots.txt, polite fetch, per-item pipeline
  pairing.py    ← cross-angle + critic pairing (deterministic, explainable)
  digest.py     ← per-day topic digest (angle breakdown + top keywords)
  scheduler.py  ← APScheduler: interval fetch + nightly digest + retention cleanup
  seed.py       ← load sources.csv
  main.py       ← FastAPI routes + startup
  static/       ← index.html, app.js, style.css (single dashboard)
run.py · requirements.txt · sources.csv · data/app.db (created at runtime)
```

---

## API (for scripting / debugging)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/feed?min_score=&angle=&include_seen=&recent_only=&date=&search=&starred_only=` | feed |
| GET | `/api/dates` | distinct days with articles (for the picker) |
| GET | `/api/digest?date=YYYY-MM-DD` | that day's topic digest |
| POST | `/api/prune` | delete non-starred articles older than the retention window |
| POST | `/api/articles/{id}/seen?seen=true` | dismiss / un-dismiss |
| POST | `/api/articles/{id}/star?starred=true` | save / un-save (star) |
| GET | `/api/sources` | list sources |
| POST | `/api/sources` `{url, angle}` | add source (+ background fetch) |
| DELETE | `/api/sources/{id}` | remove source |
| POST | `/api/sources/{id}/status?status=active|disabled` | enable/disable |
| POST | `/api/sources/{id}/refetch` | re-fetch one source |
| POST | `/api/fetch` | fetch all now (background) |
| GET | `/api/pairing?mode=cross|critic&offset=&lock_id=&min_score=` | pairing |
| GET | `/api/stats` | counts + angle list |

---

## Out of scope for v1 (and what I'd add next)

- **No LLM/embedding scoring or pairing** — keyword only, but structured for a
  drop-in swap (`_overlap_score` in `pairing.py`, `score_relevance` in
  `topic.py`). *Next:* embeddings for pairing (semantic overlap beyond shared
  words) and an LLM re-ranker for the feed.
- **No accounts / multi-user.** *Next:* trivial, but unneeded for a personal tool.
- **No full-text storage** (by policy). *Next:* would stay this way — links-out is
  intentional.
- Other nice-to-haves: article pruning/retention job, per-source health history,
  "saved pairings" for reel ideas, and OPML import/export for sources.
```
