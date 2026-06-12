#!/usr/bin/env python3
"""
Reel Topic Analyzer — local app (FastAPI)
- Groq / Gemini keys live in .env (never in the browser)
- Frontend parses the GridRank .xlsx files and sends captions+weights here
- This server asks an LLM to cluster them into semantic topics, with AUTO
  FALLBACK across free models when one is rate-limited:
      groq llama-3.3-70b -> groq llama-3.1-8b -> gemini-2.0-flash -> gemini-1.5-flash
- If every model is busy / no key set, the frontend keeps its local keyword
  result, so the tool never just breaks.

Run:  python server.py   ->  http://localhost:8000
"""
import json, time, pathlib, urllib.request, urllib.parse, urllib.error
from typing import List, Optional
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = pathlib.Path(__file__).parent.resolve()

def load_env() -> dict:
    env = {}
    p = BASE / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env

ENV = load_env()
GROQ_KEY = ENV.get("GROQ_API_KEY", "")
GEMINI_KEY = ENV.get("GEMINI_API_KEY", "")
DEFAULT_PROVIDER = ENV.get("DEFAULT_PROVIDER", "groq" if GROQ_KEY else "gemini")

GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
GEMINI_MODELS = ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]

def build_chain(preferred: Optional[str]):
    grq = [("groq", m) for m in GROQ_MODELS] if GROQ_KEY else []
    gem = [("gemini", m) for m in GEMINI_MODELS] if GEMINI_KEY else []
    return (gem + grq) if (preferred or DEFAULT_PROVIDER) == "gemini" else (grq + gem)

class RateLimited(Exception): pass
class ModelError(Exception): pass

def http_json(url, payload, headers, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode("utf-8", errors="ignore")[:300]
        except Exception: pass
        low = body.lower()
        if e.code in (429, 503) or "rate" in low or "quota" in low or "resource_exhausted" in low:
            raise RateLimited(f"{e.code}")
        raise ModelError(f"{e.code}: {body[:160]}")

def call_model(provider, model, prompt):
    if provider == "groq":
        d = http_json("https://api.groq.com/openai/v1/chat/completions",
                      {"model": model, "temperature": 0.4, "max_tokens": 4096,
                       "messages": [{"role": "user", "content": prompt}]},
                      {"Authorization": f"Bearer {GROQ_KEY}"})
        return d["choices"][0]["message"]["content"]
    else:
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={urllib.parse.quote(GEMINI_KEY)}")
        d = http_json(url, {"contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 4096}}, {})
        return "".join(p.get("text", "") for p in
                       d.get("candidates", [{}])[0].get("content", {}).get("parts", []))

def llm_fallback(prompt, preferred=None):
    chain = build_chain(preferred)
    if not chain:
        raise ModelError("No API key in .env (GROQ_API_KEY / GEMINI_API_KEY).")
    tried = []
    for pass_no in range(2):
        for provider, model in chain:
            try:
                txt = call_model(provider, model, prompt)
                if txt.strip():
                    return {"text": txt, "model": f"{provider}/{model}", "tried": tried}
                tried.append(model + "(empty)")
            except RateLimited:
                tried.append(model + "(429)")
                continue
            except Exception as e:
                tried.append(model + "(err)")
                continue
        if pass_no == 0:
            time.sleep(4)
    raise ModelError("All models busy. Tried: " + ", ".join(tried))

app = FastAPI(title="Reel Topic Analyzer")

class Video(BaseModel):
    caption: str
    creator: str = ""
    weight: float = 0

class ClusterBody(BaseModel):
    videos: List[Video]
    basis: str = "likes"
    n: int = 10
    provider: Optional[str] = None

@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")

@app.get("/api/config")
def config():
    provs = []
    if GROQ_KEY: provs.append("groq")
    if GEMINI_KEY: provs.append("gemini")
    return {"providers": provs, "default": DEFAULT_PROVIDER,
            "chain": [f"{p}/{m}" for p, m in build_chain(DEFAULT_PROVIDER)]}

@app.post("/api/cluster")
def cluster(body: ClusterBody):
    if not body.videos:
        return JSONResponse({"error": "no videos"}, status_code=400)
    # Build a compact corpus: caption + creator + weight, capped for token safety
    lines = []
    for i, v in enumerate(body.videos[:400]):
        cap = (v.caption or "").replace("\n", " ").strip()[:160]
        lines.append(f'{i}\t{v.creator}\t{int(v.weight)}\t{cap}')
    corpus = "\n".join(lines)

    prompt = f"""You are a short-form content strategist analyzing a competitor's Instagram Reels.
Below is a TSV: index, creator, {body.basis}, caption. Group these reels into the {body.n} STRONGEST
recurring TOPICS by meaning (merge synonyms and evolving phrasings — e.g. "AI tools", "AI agents",
"best apps for AI" may be one topic if they're really the same theme; but keep genuinely distinct
themes separate). Account for content drift: a topic can span slightly different wordings over time.

Rank topics by a blend of: total {body.basis} earned, how many DIFFERENT creators use it (cross-creator
themes are stronger), and number of reels. Output ONLY a JSON array, no markdown, of up to {body.n} objects:
[{{"topic":"3-5 word human topic name","why":"one short sentence on why it works","creators":<int distinct creators>,"reels":<int>,"total_{body.basis}":<int>,"example_index":<index of the single best example reel>}}]
Sort strongest first. Topic names should be specific and reusable as a reel idea, Title Case.

DATA:
{corpus}"""
    try:
        out = llm_fallback(prompt, body.provider)
        text = out["text"]
        a, b = text.find("["), text.rfind("]")
        if a < 0 or b < a:
            return JSONResponse({"error": "model returned no JSON", "raw": text[:300]}, status_code=502)
        topics = json.loads(text[a:b+1].replace("```json", "").replace("```", ""))
        return {"topics": topics, "model": out["model"], "tried": out["tried"]}
    except ModelError as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)

app.mount("/", StaticFiles(directory=str(BASE / "static"), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    if not GROQ_KEY and not GEMINI_KEY:
        print("\n!! No API key. Copy .env.example to .env and add GROQ_API_KEY (free at console.groq.com).\n")
    else:
        print("Fallback chain:", " -> ".join(f"{p}/{m}" for p, m in build_chain(DEFAULT_PROVIDER)))
    print("Reel Topic Analyzer ->  http://localhost:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
