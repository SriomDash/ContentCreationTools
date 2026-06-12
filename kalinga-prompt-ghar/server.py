#!/usr/bin/env python3
import json, re, html, time, pathlib, urllib.request, urllib.parse, urllib.error
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = pathlib.Path(__file__).parent.resolve()
PROJECTS = BASE / "projects"
PROJECTS.mkdir(exist_ok=True)

# ---------- .env loader (no extra dependency) ----------
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
GEMINI_KEY = ENV.get("GEMINI_API_KEY", "")
GROQ_KEY   = ENV.get("GROQ_API_KEY", "")
DEFAULT_PROVIDER = ENV.get("DEFAULT_PROVIDER", "gemini" if GEMINI_KEY else "groq")

# ---------- model fallback chain ----------
GEMINI_MODELS = ["gemini-3-flash-preview","gemini-3.1-flash-lite","gemini-2.5-flash"]
GROQ_MODELS   = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

def build_chain(preferred: Optional[str]) -> List[tuple]:
    gem = [("gemini", m) for m in GEMINI_MODELS] if GEMINI_KEY else []
    grq = [("groq", m) for m in GROQ_MODELS] if GROQ_KEY else []
    first = preferred or DEFAULT_PROVIDER
    return (grq + gem) if first == "groq" else (gem + grq)

class RateLimited(Exception): pass
class ModelError(Exception): pass

def http_json(url: str, payload: dict, headers: dict, timeout: int = 90) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = ""
        try: body = e.read().decode("utf-8", errors="ignore")[:400]
        except Exception: pass
        low = body.lower()
        if e.code in (429, 503) or "resource_exhausted" in low or "rate_limit" in low or "quota" in low:
            raise RateLimited(f"{e.code}: {body[:160]}")
        raise ModelError(f"{e.code}: {body[:200]}")

def call_model(provider: str, model: str, prompt: str) -> str:
    if provider == "gemini":
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={urllib.parse.quote(GEMINI_KEY)}")
        d = http_json(url, {"contents": [{"parts": [{"text": prompt}]}],
                            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096}}, {})
        return "".join(p.get("text", "") for p in
                       d.get("candidates", [{}])[0].get("content", {}).get("parts", []))
    else:
        d = http_json("https://api.groq.com/openai/v1/chat/completions",
                      {"model": model, "temperature": 0.7, "max_tokens": 4096,
                       "messages": [{"role": "user", "content": prompt}]},
                      {"Authorization": f"Bearer {GROQ_KEY}"})
        return d["choices"][0]["message"]["content"]

def llm_with_fallback(prompt: str, preferred: Optional[str] = None) -> dict:
    """Walk the model chain; skip rate-limited models; two passes with backoff."""
    chain = build_chain(preferred)
    if not chain:
        raise ModelError("No API key found in .env (GEMINI_API_KEY / GROQ_API_KEY).")
    attempts = []
    for pass_no in range(2):                       # two full passes through the chain
        for provider, model in chain:
            try:
                text = call_model(provider, model, prompt)
                if text.strip():
                    if attempts:
                        print(f"[fallback] served by {provider}/{model} after: {', '.join(attempts)}")
                    return {"text": text, "provider": provider, "model": model,
                            "fallbacks": attempts}
                attempts.append(f"{model} (empty)")
            except RateLimited:
                attempts.append(f"{model} (rate limited)")
                print(f"[fallback] {provider}/{model} rate limited -> trying next model")
                continue
            except ModelError as e:
                attempts.append(f"{model} (error)")
                print(f"[fallback] {provider}/{model} error: {e} -> trying next model")
                continue
            except Exception as e:
                attempts.append(f"{model} (network)")
                print(f"[fallback] {provider}/{model} network issue: {e}")
                continue
        if pass_no == 0:
            print("[fallback] whole chain busy — waiting 5s for a second pass…")
            time.sleep(5)
    raise ModelError("All models are rate-limited right now. Wait a minute and try again. "
                     f"Tried: {', '.join(attempts)}")

def slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9 _-]", "", name).strip().replace(" ", "-").lower()
    return s[:60] or "untitled"

class ProjectBody(BaseModel):
    name: str = ""

class ReadBody(BaseModel):
    urls: List[str] = []

class LLMBody(BaseModel):
    prompt: str
    provider: Optional[str] = None

class ResearchBody(BaseModel):
    text: str = ""          
    urls: List[str] = []   

class SaveBody(BaseModel):
    project: str
    filename: str = "out.md"
    content: str = ""

# ---------- app & routes ----------
app = FastAPI(title="Kalinga Prompt Ghar")

@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")

@app.get("/api/config")
def config():
    providers = []
    if GEMINI_KEY: providers.append("gemini")
    if GROQ_KEY:   providers.append("groq")
    return {"providers": providers, "default": DEFAULT_PROVIDER,
            "chain": [f"{p}/{m}" for p, m in build_chain(DEFAULT_PROVIDER)]}

@app.get("/api/projects")
def list_projects():
    names = sorted([p.name for p in PROJECTS.iterdir() if p.is_dir()])
    return {"projects": names}

@app.post("/api/projects")
def create_project(body: ProjectBody):
    name = slugify(body.name)
    pdir = PROJECTS / name
    (pdir / "photos").mkdir(parents=True, exist_ok=True)
    return {"project": name, "path": str(pdir)}

@app.post("/api/read")
def read_urls(body: ReadBody):
    """Server-side article reading: jina reader first, raw fetch + tag-strip fallback."""
    out = []
    for url in body.urls[:5]:
        text, err = "", ""
        for attempt in (f"https://r.jina.ai/{url}", url):
            try:
                req = urllib.request.Request(attempt, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read().decode("utf-8", errors="ignore")
                if attempt.startswith("https://r.jina.ai/"):
                    text = raw
                else:
                    raw = re.sub(r"(?is)<(script|style|nav|footer|header|aside).*?</\1>", " ", raw)
                    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
                    text = re.sub(r"\s{3,}", "\n", text)
                if len(text.strip()) > 200:
                    break
            except Exception as e:
                err = str(e)
        if len(text.strip()) > 200:
            out.append({"url": url, "ok": True, "chars": len(text), "text": text[:15000]})
        else:
            out.append({"url": url, "ok": False, "error": err or "empty page"})
    return {"sources": out}

def gemini_grounded(prompt: str) -> dict:
    """Call Gemini with the Google Search tool so it returns REAL, current URLs.
    Returns {topic, sources:[{title,url,snippet}], model}. Requires GEMINI_KEY."""
    if not GEMINI_KEY:
        raise ModelError("Finding related URLs needs a GEMINI_API_KEY in .env (free at aistudio.google.com).")
    last = ""
    for model in GEMINI_MODELS:
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={urllib.parse.quote(GEMINI_KEY)}")
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048},
        }
        try:
            d = http_json(url, payload, {}, timeout=60)
        except RateLimited:
            last = "rate limited"; continue
        except Exception as e:
            last = str(e); continue
        cand = (d.get("candidates") or [{}])[0]
        sources, seen = [], set()
        gm = cand.get("groundingMetadata", {}) or {}
        for chunk in gm.get("groundingChunks", []) or []:
            web = (chunk or {}).get("web", {}) or {}
            u = web.get("uri") or web.get("url")
            t = web.get("title") or u
            if u and u not in seen:
                seen.add(u); sources.append({"title": t, "url": u, "snippet": ""})
        text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
        topic = ""
        try:
            a, b = text.find("{"), text.rfind("}")
            if a > -1 and b > a:
                obj = json.loads(text[a:b + 1])
                topic = obj.get("topic", "")
                for s in obj.get("sources", []) or []:
                    u = s.get("url", "")
                    if u and u not in seen:
                        seen.add(u); sources.append({"title": s.get("title", u), "url": u, "snippet": s.get("snippet", "")})
                    elif u:
                        for ex in sources:
                            if ex["url"] == u and not ex["snippet"]:
                                ex["snippet"] = s.get("snippet", "")
        except Exception:
            pass
        if sources:
            return {"topic": topic, "sources": sources, "model": f"gemini/{model}"}
        last = "no sources returned"
    raise ModelError("Could not fetch related sources (" + last + ").")

@app.post("/api/research")
def research(body: ResearchBody):
    """Understand the article, then use Gemini Google Search to find more URLs on the same
    topic. Returns related sources for the user to APPROVE before continuing."""
    article = (body.text or "").strip()[:6000]
    if not article:
        return JSONResponse({"error": "no article text to analyze"}, status_code=400)
    avoid = ", ".join(body.urls[:5])
    prompt = (
        "You are a research assistant for a tech & AI content brand.\n"
        "1) Read the ARTICLE below and identify its core topic in a few words.\n"
        "2) Use Google Search to find 6-8 high-quality, CURRENT articles on the SAME topic "
        "from reputable sources, to broaden the coverage. Avoid these already-used URLs: "
        f"{avoid or '(none)'}.\n"
        "Return ONLY a JSON object, no markdown:\n"
        '{"topic":"short topic","sources":[{"title":"...","url":"https://...","snippet":"one line why it is relevant"}]}\n\n'
        "ARTICLE:\n" + article
    )
    try:
        return gemini_grounded(prompt)
    except ModelError as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)

@app.post("/api/llm")
def llm(body: LLMBody):
    try:
        return llm_with_fallback(body.prompt, body.provider)
    except ModelError as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)

@app.post("/api/save")
def save_file(body: SaveBody):
    project = slugify(body.project)
    filename = pathlib.Path(body.filename).name          # no path tricks
    if not filename.endswith((".md", ".json", ".txt")):
        return JSONResponse({"error": "only .md/.json/.txt"}, status_code=400)
    pdir = PROJECTS / project
    if not pdir.exists():
        return JSONResponse({"error": "project not found"}, status_code=404)
    (pdir / filename).write_text(body.content, encoding="utf-8")
    return {"saved": str(pdir / filename)}

@app.post("/api/upload/{project}")
def upload_photo(project: str, photos: List[UploadFile] = File(...)):
    pdir = PROJECTS / slugify(project) / "photos"
    if not pdir.exists():
        return JSONResponse({"error": "project not found"}, status_code=404)
    saved = []
    for f in photos:
        name = pathlib.Path(f.filename or "").name
        if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            continue
        (pdir / name).write_bytes(f.file.read())
        saved.append(name)
    return {"saved": saved}

@app.get("/api/project/{project}/files")
def project_files(project: str):
    pdir = PROJECTS / slugify(project)
    if not pdir.exists():
        return JSONResponse({"error": "project not found"}, status_code=404)
    docs = [p.name for p in pdir.iterdir() if p.is_file()]
    photos = [p.name for p in (pdir / "photos").iterdir() if p.is_file()] if (pdir / "photos").exists() else []
    return {"docs": docs, "photos": photos}

app.mount("/", StaticFiles(directory=str(BASE / "static"), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    if not GEMINI_KEY and not GROQ_KEY:
        print("\n!! No API keys found. Copy .env.example to .env and add at least one key.\n")
    else:
        chain = " -> ".join(f"{p}/{m}" for p, m in build_chain(DEFAULT_PROVIDER))
        print(f"Fallback chain: {chain}")
    print("Kalinga Prompt Ghar ->  http://localhost:8000")
    uvicorn.run(app, host="127.0.0.1", port=8000)
