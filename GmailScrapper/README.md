# Newsletter Digest — local, READ-ONLY Gmail triage

A small local tool that scans **one** Gmail label of newsletters, keeps every
newsletter, extracts the article links inside each one, flags the tech/AI ones,
scores them, and shows a ranked daily digest so you can click straight through
to what matters. It **triages and surfaces** — it never acts on your mailbox.

Companion to your content-research aggregator: it reuses the same **two-gate
tech/AI filter + weighted keyword-scoring** approach, kept in one editable
config so the two tools stay consistent.

## ⚠️ READ-ONLY — the hard guarantee

- Uses the `gmail.readonly` scope **only**. It never deletes, archives,
  marks-read, modifies, labels, moves, or sends anything in Gmail.
- The scope is hardcoded in [`auth.py`](auth.py) and **asserted at runtime** — if
  the token ever carried a broader scope, the app refuses to run rather than use
  write access. There is no code path that calls anything but
  `messages.list` / `messages.get` / `labels.list`.
- It reads messages under **one label you specify** (default `AI-News`), never
  your whole inbox.
- "Seen" status lives only in the local app database. Marking a link seen here
  does **not** touch Gmail.
- Nothing is uploaded anywhere. No email content is sent to any external service.
  Everything stays in a local SQLite file.

## Setup

Auth is already configured in this folder (`credentials.json` + `token.json`,
`gmail.readonly`, `run_local_server` on port 9090). Just install deps:

```bash
pip install -r requirements.txt
```

## Run (two commands)

```bash
# 1. Scan the label and build/update the local digest DB (read-only)
python ingest.py

# 2. Serve the digest page
python app.py         # open http://127.0.0.1:8000
```

`ingest.py` options:

```bash
python ingest.py --days 5              # widen the look-back window for one run
python ingest.py --label "My Label"    # scan a different label for one run
```

Re-run `ingest.py` whenever you want fresh newsletters (e.g. daily). It's
incremental: existing links keep their "seen" state, new ones are added.

## Configure — everything editable is in [`config.py`](config.py)

| Setting | What it does |
|---|---|
| `LABEL` | The one Gmail label to scan. **Default `AI-News`.** If the label isn't found, `ingest.py` prints your available label names so you can copy the exact one. |
| `SINCE_DAYS` | Rolling look-back window (default `2`). |
| `KEYWORDS` | **The tech/AI keyword set + weights.** This is the knob you'll touch most — add/remove terms and retune weights. Matched as whole words. |
| `SCORE_SATURATION` | How fast the 0–1 relevance score saturates (lower = easier to hit high scores). |
| `SNIPPET_WEIGHT_FACTOR` | How much a keyword found only in the surrounding paragraph (not the link's own anchor text) counts, relative to an anchor match. Default `0.35`. |
| `SNIPPET_ONLY_SCORE_CAP` | Hard ceiling on a link whose anchor matched no keyword (signal came purely from context). Default `0.5` — keeps context-only links in play but stops "read more"/"said" from outranking a real headline. |
| `NEGATIVE_KEYWORDS` | Whole-word terms that subtract from the score (webinar, sponsored, discount…). If they cancel the positives, the link is no longer flagged tech/AI. |
| `BOILERPLATE_MARKERS` / `BOILERPLATE_HOSTS` | Gate 1 rules: what counts as newsletter chrome (unsubscribe, view-in-browser, social) vs a real article link. |

### The two-gate filter (mirrors the aggregator)

1. **Gate 1 — structural.** Is this a real outbound article link, or newsletter
   boilerplate (unsubscribe / view-in-browser / social/share / mailto)?
   Boilerplate is still stored (nothing discarded) but marked `is_article=0`, so
   it drops into the collapsed **"other links"** pile.
2. **Gate 2 — topical.** Does the link's **anchor text + surrounding snippet**
   match a tech/AI keyword? Broad, err-toward-inclusion. Whole-word matching
   means `AI` never fires on "email"/"again"/"detail", and `tech` is whole-word.

**Score (0–1):** weighted keyword overlap, saturating-normalized. Keywords in
the link's **anchor text** count at full weight; keywords found only in the
**surrounding snippet** count at `SNIPPET_WEIGHT_FACTOR`, and a context-only link
is capped at `SNIPPET_ONLY_SCORE_CAP` — so a link whose own headline is about AI
always outranks a stray "read more" sitting in an AI paragraph. Negative
keywords subtract. The matched keywords are stored and shown as **chips** on each
flagged link, so you can see exactly why it scored and tune `KEYWORDS`
accordingly. The score drives both the highlight and the sort order.

## Digest view

- **Grouped by newsletter.** Every newsletter appears as a card (sender,
  subject, date, "N tech/AI links") — even ones with zero flagged links.
- Cards are **sorted by tech/AI density** — the newsletter with the
  most / highest-scoring links floats to the top.
- Inside each card, **tech/AI links are highlighted with their score**;
  non-flagged links are collapsed under a greyed **"N other links"** toggle so
  you can still reach them without clutter.
- Every link is **click-through** (opens the real article in a new tab).
- A global **min-relevance slider** hides low-scoring links.
- A per-link **"mark seen"** toggle dims read items (app-side only).

## Data model (SQLite, `digest.db`)

- **messages**: `id` (gmail msg id), `sender`, `subject`, `received_at`,
  `label`, `created_at`.
- **links**: `id`, `message_id` (fk), `url` (cleaned/canonical), `anchor_text`,
  `snippet`, `is_article` (Gate 1), `is_ai` (Gate 2), `score` (0–1), `seen`.
  Unique on `(message_id, url)`.

To start fresh, just delete `digest.db` and re-run `ingest.py`.

## Link cleaning

Each extracted URL is cleaned before storage: `utm_*` and other tracking params
are stripped, common `?url=` / `?u=` / path-embedded click-redirects are
unwrapped to the real destination **where possible**, and links are deduped
within and across emails. Some providers (e.g. beehiiv `/ss/c/…`) encode the
destination in an opaque blob that can't be decoded without following the
redirect over the network — which this tool deliberately does **not** do. Those
links are kept as-is and still click through correctly via the browser redirect.

## Logging

Each `ingest.py` run logs, per newsletter and as a run total: newsletters
scanned, links extracted, links treated as boilerplate, and links flagged
tech/AI.

## Not in v1 (easy to add later)

- **LLM scoring.** Scoring is keyword-only today. `classify.py` is the single
  swap point — a model-based scorer could replace `score_text()` while keeping
  the same two-gate structure and DB schema.
- No write access to Gmail of any kind, no auto-actions. Single user, local.
