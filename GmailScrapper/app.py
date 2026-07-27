"""
app.py — lightweight local FastAPI server for the digest page.

  GET  /              single-page digest UI
  GET  /api/digest    newsletters + links as JSON
  POST /api/seen      mark a link seen/unseen (APP-SIDE ONLY; never touches Gmail)

Run:  python app.py     ->  http://127.0.0.1:8000
This server reads the local SQLite DB built by ingest.py. It makes NO Gmail
calls at all, so browsing the digest can never modify your mailbox.
"""

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import config
import db

app = FastAPI(title="Newsletter Digest (read-only)")


class SeenBody(BaseModel):
    link_id: int
    seen: bool


@app.get("/api/digest")
def api_digest():
    messages = db.fetch_digest(config.DB_PATH)
    # Sort newsletters: those with the most / highest-scoring tech/AI links first.
    def rank(m):
        ai = [l for l in m["links"] if l["is_ai"]]
        top = max((l["score"] for l in ai), default=0)
        return (top, len(ai), m["received_at"] or 0)
    messages.sort(key=rank, reverse=True)
    for m in messages:
        m["ai_count"] = sum(1 for l in m["links"] if l["is_ai"])
    return JSONResponse(messages)


@app.post("/api/seen")
def api_seen(body: SeenBody):
    db.set_seen(config.DB_PATH, body.link_id, body.seen)
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    return HTML


HTML = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Newsletter Digest</title>
<style>
  :root { --bg:#0f1115; --card:#171a21; --edge:#242833; --text:#e6e8ee;
          --muted:#8b93a5; --accent:#5b9dff; --ai:#1e2a1f; --aiedge:#2f6b3a;
          --chip:#232838; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }
  header { position:sticky; top:0; z-index:5; background:rgba(15,17,21,.95);
           backdrop-filter:blur(6px); border-bottom:1px solid var(--edge);
           padding:14px 20px; display:flex; gap:18px; align-items:center;
           flex-wrap:wrap; }
  h1 { font-size:17px; margin:0; font-weight:650; }
  .ro { font-size:11px; color:#9fe0a8; border:1px solid var(--aiedge);
        padding:2px 8px; border-radius:20px; }
  .controls { display:flex; gap:16px; align-items:center; margin-left:auto;
              flex-wrap:wrap; font-size:13px; color:var(--muted); }
  .controls input[type=range]{ vertical-align:middle; }
  main { max-width:900px; margin:0 auto; padding:20px; }
  .card { background:var(--card); border:1px solid var(--edge);
          border-radius:12px; margin:0 0 16px; overflow:hidden; }
  .card-head { padding:14px 16px; display:flex; gap:10px; align-items:baseline;
               flex-wrap:wrap; border-bottom:1px solid var(--edge); }
  .subject { font-weight:600; font-size:15px; }
  .sender { color:var(--muted); font-size:12.5px; }
  .date { color:var(--muted); font-size:12px; margin-left:auto; white-space:nowrap; }
  .count { font-size:12px; color:#9fe0a8; }
  .count.zero { color:var(--muted); }
  ul { list-style:none; margin:0; padding:0; }
  li.link { padding:9px 16px; border-bottom:1px solid #1e222c; display:flex;
            gap:10px; align-items:flex-start; }
  li.link:last-child { border-bottom:none; }
  li.ai { background:var(--ai); }
  li.seen { opacity:.4; }
  .score { font-variant-numeric:tabular-nums; font-size:11px; color:#9fe0a8;
           border:1px solid var(--aiedge); border-radius:6px; padding:1px 6px;
           margin-top:2px; white-space:nowrap; }
  a.link-a { color:var(--text); text-decoration:none; word-break:break-word; }
  li.ai a.link-a { color:#d7f5db; font-weight:550; }
  a.link-a:hover { text-decoration:underline; }
  .host { display:block; font-size:11px; color:var(--muted); margin-top:1px; }
  .chips { margin-top:4px; display:flex; gap:4px; flex-wrap:wrap; }
  .chip { font-size:10px; color:#9fe0a8; background:rgba(47,107,58,.25);
          border:1px solid var(--aiedge); border-radius:10px; padding:0 7px;
          line-height:16px; }
  .seenbtn { background:var(--chip); border:1px solid var(--edge); color:var(--muted);
             font-size:11px; border-radius:6px; padding:2px 7px; cursor:pointer;
             margin-left:auto; white-space:nowrap; }
  .seenbtn:hover { color:var(--text); }
  .other-toggle { padding:9px 16px; color:var(--muted); font-size:12.5px;
                  cursor:pointer; user-select:none; }
  .other-toggle:hover { color:var(--text); }
  .other { display:none; }
  .other.open { display:block; }
  li.other-link a.link-a { color:var(--muted); }
  .empty { color:var(--muted); text-align:center; padding:60px 0; }
  .kw { color:var(--muted); font-size:11px; }
</style>
</head>
<body>
<header>
  <h1>📥 Newsletter Digest</h1>
  <span class="ro">READ-ONLY · never modifies Gmail</span>
  <div class="controls">
    <label>min relevance <b id="minv">0.00</b><br>
      <input id="minrel" type="range" min="0" max="1" step="0.05" value="0"></label>
    <label><input id="hideseen" type="checkbox"> hide seen</label>
  </div>
</header>
<main id="root"><div class="empty">Loading…</div></main>

<script>
let DATA = [];
let minRel = 0;
let hideSeen = false;

function host(u){ try { return new URL(u).host.replace(/^www\\./,''); } catch(e){ return ''; } }
function fmtDate(sec){ if(!sec) return ''; const d=new Date(sec*1000);
  return d.toLocaleDateString(undefined,{month:'short',day:'numeric'}) + ' ' +
         d.toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'}); }

async function load(){
  DATA = await (await fetch('/api/digest')).json();
  render();
}

async function toggleSeen(link, el){
  link.seen = link.seen ? 0 : 1;
  await fetch('/api/seen', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({link_id: link.id, seen: !!link.seen})});
  render();
}

function linkRow(l, isOther){
  const li = document.createElement('li');
  li.className = 'link' + (l.is_ai ? ' ai':'') + (isOther?' other-link':'') + (l.seen?' seen':'');
  if(l.is_ai){
    const s=document.createElement('span'); s.className='score';
    s.textContent = Number(l.score).toFixed(2); li.appendChild(s);
  }
  const wrap=document.createElement('div'); wrap.style.flex='1';
  const a=document.createElement('a'); a.className='link-a'; a.href=l.url;
  a.target='_blank'; a.rel='noopener noreferrer';
  a.textContent = l.anchor_text && l.anchor_text.trim() ? l.anchor_text : l.url;
  wrap.appendChild(a);
  const h=document.createElement('span'); h.className='host'; h.textContent=host(l.url);
  wrap.appendChild(h);
  if(l.is_ai && l.matched){
    const chips=document.createElement('div'); chips.className='chips';
    l.matched.split(',').map(s=>s.trim()).filter(Boolean).slice(0,6).forEach(kw=>{
      const c=document.createElement('span'); c.className='chip'; c.textContent=kw;
      chips.appendChild(c);
    });
    wrap.appendChild(chips);
  }
  li.appendChild(wrap);
  const b=document.createElement('button'); b.className='seenbtn';
  b.textContent = l.seen ? 'seen ✓' : 'mark seen';
  b.onclick=()=>toggleSeen(l,li); li.appendChild(b);
  return li;
}

function render(){
  minRel = parseFloat(document.getElementById('minrel').value);
  hideSeen = document.getElementById('hideseen').checked;
  document.getElementById('minv').textContent = minRel.toFixed(2);
  const root = document.getElementById('root');
  root.innerHTML='';

  let shown=0;
  for(const m of DATA){
    const aiLinks = m.links.filter(l=> l.is_ai && l.score>=minRel && !(hideSeen&&l.seen));
    const otherLinks = m.links.filter(l=> !l.is_ai && !(hideSeen&&l.seen));
    // Every newsletter is kept and shown (even 0 flagged), per spec.
    const card=document.createElement('div'); card.className='card';

    const head=document.createElement('div'); head.className='card-head';
    const subj=document.createElement('span'); subj.className='subject'; subj.textContent=m.subject;
    const snd=document.createElement('span'); snd.className='sender'; snd.textContent=m.sender;
    const dt=document.createElement('span'); dt.className='date'; dt.textContent=fmtDate(m.received_at);
    head.appendChild(subj); head.appendChild(snd);
    const cnt=document.createElement('span');
    cnt.className='count'+(m.ai_count?'':' zero');
    cnt.textContent = m.ai_count ? (m.ai_count+' tech/AI link'+(m.ai_count>1?'s':'')) : 'no tech/AI links';
    head.appendChild(cnt); head.appendChild(dt);
    card.appendChild(head);

    const ul=document.createElement('ul');
    aiLinks.forEach(l=> ul.appendChild(linkRow(l,false)));
    card.appendChild(ul);

    if(otherLinks.length){
      const tog=document.createElement('div'); tog.className='other-toggle';
      tog.textContent = '▸ '+otherLinks.length+' other link'+(otherLinks.length>1?'s':'');
      const ou=document.createElement('ul'); ou.className='other';
      otherLinks.forEach(l=> ou.appendChild(linkRow(l,true)));
      tog.onclick=()=>{ ou.classList.toggle('open');
        tog.textContent=(ou.classList.contains('open')?'▾ ':'▸ ')+otherLinks.length+
          ' other link'+(otherLinks.length>1?'s':''); };
      card.appendChild(tog); card.appendChild(ou);
    }
    root.appendChild(card); shown++;
  }
  if(!shown) root.innerHTML='<div class="empty">No newsletters yet. Run <code>python ingest.py</code> first.</div>';
}

document.getElementById('minrel').addEventListener('input', render);
document.getElementById('hideseen').addEventListener('change', render);
load();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.PORT)
