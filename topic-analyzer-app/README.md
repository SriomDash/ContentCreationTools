# Reel Topic Analyzer (AI app)

Reads your **GridRank Excel exports** and uses a **free LLM (Groq/Gemini)** to cluster the
reels into the strongest **reel topics** — merging synonyms and handling content drift, so
evolving themes ("AI tools" -> "AI agents") count as one topic instead of scattering.

Keys live in `.env`, never in the browser. If the AI is rate-limited or no key is set, it
automatically falls back to a fast **local keyword** analysis, so it never just breaks.

## Setup (one time)
1. Install Python 3.9+
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env`, add a free key:
   - Groq (recommended): https://console.groq.com -> API Keys
   - Gemini: https://aistudio.google.com -> Get API key

## Run
```
python server.py
```
Open http://localhost:8000

## Use
1. Drag in as many `gridrank_*.xlsx` files as you want.
2. Optional: set a start date, pick how many topics, choose AI or local.
3. Click **Find Top Topics**.

Each topic shows why it works, how many creators use it (★ proven = 2+), reels, total
likes/views, and a clickable example. Copy as text or download a Markdown report.

## Auto model fallback
groq llama-3.3-70b -> groq llama-3.1-8b -> gemini-2.0-flash -> gemini-2.0-flash-lite -> gemini-1.5-flash
(order starts from DEFAULT_PROVIDER; add both keys for the strongest safety net).
Every hop is printed in the terminal. If all are busy, you still get the local result.
