# Kalinga Prompt Ghar

Local prompt factory for Instagram carousels in the Kalinga Code design system.
Sources in -> slide plan -> editable rows -> style-locked Nano Banana prompts out.
Free backends with AUTO FALLBACK: when one free model hits its rate limit (429 / quota),
the server automatically tries the next one in the chain:
`gemini-2.0-flash -> gemini-2.0-flash-lite -> gemini-1.5-flash -> groq llama-3.3-70b -> groq llama-3.1-8b`
(order starts from your DEFAULT_PROVIDER; if all are busy it waits 5s and retries the chain once).
Add BOTH keys to .env for the strongest fallback safety net. Keys live in `.env`, never in the UI.

## Setup (one time)

1. Install Python 3.9+ (python.org)
2. In this folder, run:
   ```
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and paste at least one free key:
   - Gemini key: https://aistudio.google.com -> "Get API key"
   - Groq key:   https://console.groq.com -> "API Keys"

## Note on the Research step
Finding related URLs uses Gemini's Google Search grounding, so the Research step specifically needs a GEMINI_API_KEY in .env (free at aistudio.google.com). The rest of the app still works with just a Groq key; if no Gemini key is set, simply use 'skip — use my sources only' on the Research screen.

## Run

```
python server.py
```
(or `uvicorn server:app --port 8000`)
Open http://localhost:8000 in your browser.

## Flow

1. **Project** - type a name. A folder `projects/<name>/` is created with a `photos/` subfolder.
2. **Sources** - paste up to 5 URLs (or raw text). The server reads them.
3. **Research** - the app understands your article's topic, uses Gemini Google Search to find more current sources on the same topic, and shows them as a checklist. Tick the ones to include and click Approve — only approved sources move forward. You can also skip and use only your own.
4. **Slides** - pick 3 to 8.
5. **Plan** - one editable row per slide (edit button per row). Auto-saves `plan.json`.
6. **Prompts** - style-locked, square 1:1, English-only prompts. Auto-saved as
   `projects/<name>/prompts.md`. Drag-drop the images Nano Banana generates into the
   drop zone to store them in `projects/<name>/photos/`.

## Why prompts stay consistent

The Kalinga Code "style DNA" paragraphs are hard-coded in `static/index.html` (the `DNA`
object). The AI only fills four slots per slide: headline, punch, scene, tags. The app
assembles the final prompt around them, so the brand language is identical every time.
To evolve the style, edit the DNA object - that is your single source of truth.

## Project folder layout

```
projects/
  fable5-launch/
    plan.json      <- the slide plan
    prompts.md     <- the generated prompts doc
    photos/        <- drop your generated images here
```

## Troubleshooting

- "Server not reachable" -> run `python server.py` first.
- "No API key found" -> check the `.env` file exists next to `server.py` and restart.
- A URL fails to read -> paste the article text into the fallback box instead.
- Model returns bad JSON -> just click the button again (free models hiccup sometimes).
- "All models are rate-limited" -> the whole chain is busy; wait ~1 minute. Adding the second
  provider's key to .env usually makes this disappear entirely.
- Watch the terminal while it runs: every fallback hop is logged, e.g.
  `[fallback] gemini/gemini-2.0-flash rate limited -> trying next model`.
