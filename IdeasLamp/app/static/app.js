"use strict";

const state = {
  minScore: 0.2,
  angle: null,          // null = all
  includeSeen: false,
  date: null,           // null = all days; else "YYYY-MM-DD"
  search: "",           // free-text keyword query
  savedOnly: false,     // show only starred (saved) articles
  pairMode: "cross",
  pairOffset: 0,
  lockId: null,
  angles: [],
  criticAngle: "critic",
};

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, html) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
};

function toast(msg) {
  const t = el("div", "toast", msg);
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2600);
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return r.json();
}

const esc = (s) => (s || "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function fmtDate(iso) {
  if (!iso) return "no date";
  const d = new Date(iso);
  if (isNaN(d)) return "no date";
  const diff = (Date.now() - d.getTime()) / 36e5;
  if (diff < 1) return Math.max(1, Math.round(diff * 60)) + "m ago";
  if (diff < 24) return Math.round(diff) + "h ago";
  if (diff < 24 * 7) return Math.round(diff / 24) + "d ago";
  return d.toLocaleDateString();
}

// ---------------------------------------------------------------- stats + chips
async function loadStats() {
  const s = await api("/api/stats");
  state.angles = s.angles;
  state.criticAngle = s.critic_angle;
  const c = s.counts;
  $("#stats").innerHTML =
    `<span><b>${c.articles_unseen}</b> in feed</span>` +
    `<span><b>${c.articles_starred || 0}</b> ★ saved</span>` +
    `<span><b>${c.articles_critic}</b> critic-tagged</span>` +
    `<span><b>${c.sources_active}</b> active sources</span>` +
    `<span><b>${c.sources_blocked}</b> blocked</span>` +
    `<span><b>${c.sources_no_feed}</b> no-feed</span>`;
  buildChips();
}

function buildChips() {
  const wrap = $("#angle-chips");
  wrap.innerHTML = "";
  const mk = (label, val, dataA) => {
    const chip = el("div", "chip", label);
    chip.dataset.a = dataA;
    if (state.angle === val) chip.classList.add("active");
    chip.onclick = () => { state.angle = (state.angle === val ? null : val); buildChips(); loadFeed(); };
    wrap.appendChild(chip);
  };
  mk("all", null, "all");
  state.angles.forEach((a) => mk(a, a, a));
  mk("critic", state.criticAngle, "critic");
}

// ---------------------------------------------------------------- dates + digest
async function loadDates() {
  try {
    const data = await api("/api/dates");
    const dl = $("#active-dates");
    dl.innerHTML = data.dates.map((d) => `<option value="${d}">`).join("");
  } catch (e) {}
}

async function loadDigest() {
  const strip = $("#digest-strip");
  if (!state.date) { strip.hidden = true; strip.innerHTML = ""; return; }
  const { digest } = await api("/api/digest?date=" + encodeURIComponent(state.date));
  strip.hidden = false;
  if (!digest.total) {
    strip.innerHTML = `<span class="digest-title">${state.date}</span>
      <span class="digest-empty">No topics posted on this day.</span>`;
    return;
  }
  const angles = digest.by_angle.map(([a, n]) =>
    `<span class="tag ${a === 'critic' ? 'critic' : angClass(a)}">${a} ${n}</span>`).join("");
  const kws = digest.top_keywords.slice(0, 10).map(([k, n]) =>
    `<span class="term">${esc(k)} ·${n}</span>`).join("");
  strip.innerHTML =
    `<div class="digest-head">
       <span class="digest-title">📅 ${digest.date}</span>
       <span class="digest-count">${digest.total} articles · ${digest.sources} sources · ${digest.critic_count} critic</span>
     </div>
     <div class="digest-row"><span class="digest-label">angles</span>${angles}</div>
     <div class="digest-row"><span class="digest-label">topics</span>${kws}</div>`;
}

// ---------------------------------------------------------------- feed
async function loadFeed() {
  const params = new URLSearchParams({
    min_score: state.minScore,
    include_seen: state.includeSeen,
  });
  if (state.angle) params.set("angle", state.angle);
  if (state.date) params.set("date", state.date);
  if (state.search) params.set("search", state.search);
  if (state.savedOnly) params.set("starred_only", "true");
  const data = await api("/api/feed?" + params.toString());
  const feed = $("#feed");
  feed.innerHTML = "";
  if (!data.articles.length) {
    let hint;
    if (state.savedOnly) hint = "No saved articles yet. Click the ☆ on any card to save it here — saved items are kept forever, even past 10 days.";
    else if (state.search) hint = `No matches for “${state.search}”. Try different keywords.`;
    else if (state.date) hint = `No articles for ${state.date}. Try another day or clear the date filter.`;
    else hint = "No articles match. Lower the min-relevance, clear the angle filter, or hit “Fetch now”. First fetch can take a minute.";
    feed.appendChild(el("div", "empty", hint));
    return;
  }
  data.articles.forEach((a) => feed.appendChild(renderCard(a)));
}

const KNOWN_ANGLES = ["tech","biology","philosophy","psychology","climate","culture","market"];
const angClass = (ang) => KNOWN_ANGLES.includes(ang) ? `ang-${ang}` : "";

function angleTags(a) {
  let tags = "";
  if (a.is_critic) tags += `<span class="tag critic">CRITIC</span>`;
  tags += `<span class="tag primary ${angClass(a.primary_angle)}">${esc(a.primary_angle)}</span>`;
  (a.angles || []).forEach((ang) => {
    if (ang !== a.primary_angle) tags += `<span class="tag ${angClass(ang)}">${esc(ang)}</span>`;
  });
  return tags;
}

function renderCard(a) {
  const card = el("div", "card" + (a.is_critic ? " is-critic" : ""));
  card.dataset.angle = a.primary_angle;
  card.innerHTML =
    `<div class="card-tools">
       <button class="star${a.starred ? " on" : ""}" title="Save for reference">${a.starred ? "★" : "☆"}</button>
       <button class="dismiss" title="Dismiss">&times;</button>
     </div>
     <div class="card-top">
       <span class="source"><span class="dot"></span><span class="name">${esc(a.source || "")}</span></span>
       <span class="time">${fmtDate(a.published_at)}</span>
     </div>
     <h3><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title)}</a></h3>
     ${a.summary ? `<p class="summary">${esc(a.summary)}</p>` : ""}
     <div class="card-foot">
       <div class="tags">${angleTags(a)}</div>
       <span class="score-badge">${a.score.toFixed(2)}</span>
     </div>`;
  const starBtn = card.querySelector(".star");
  starBtn.onclick = async () => {
    const next = !a.starred;
    await api(`/api/articles/${a.id}/star?starred=${next}`, { method: "POST" });
    a.starred = next;
    starBtn.classList.toggle("on", next);
    starBtn.textContent = next ? "★" : "☆";
    starBtn.title = next ? "Saved — click to unsave" : "Save for reference";
    loadStats();
    if (state.savedOnly && !next) card.remove(); // removed from the Saved view
  };
  card.querySelector(".dismiss").onclick = async () => {
    await api(`/api/articles/${a.id}/seen?seen=true`, { method: "POST" });
    card.remove();
    loadStats();
  };
  return card;
}

// ---------------------------------------------------------------- pairing
function highlight(text, terms) {
  let out = esc(text || "");
  terms.forEach((t) => {
    const re = new RegExp("(" + t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")", "ig");
    out = out.replace(re, "<mark>$1</mark>");
  });
  return out;
}

function pairCard(art, terms, side) {
  const c = el("div", "pair-card" + (art.is_critic ? " is-critic" : ""));
  c.dataset.angle = art.primary_angle;
  const locked = state.lockId === art.id;
  c.innerHTML =
    `<div class="tags">${angleTags(art)}</div>
     <h3><a href="${esc(art.url)}" target="_blank" rel="noopener">${highlight(art.title, terms)}</a></h3>
     <div class="time">${esc(art.source || "")} &middot; ${fmtDate(art.published_at)} &middot; score ${art.score.toFixed(2)}</div>
     ${art.summary ? `<p class="summary" style="margin-top:8px">${highlight(art.summary.slice(0, 200), terms)}…</p>` : ""}
     <button class="btn ghost tiny lock-btn">${locked ? "🔒 Locked — unlock" : "Lock this one"}</button>`;
  c.querySelector(".lock-btn").onclick = () => {
    state.lockId = locked ? null : art.id;
    state.pairOffset = 0;
    findPairing();
  };
  return c;
}

async function findPairing() {
  const params = new URLSearchParams({
    mode: state.pairMode, offset: state.pairOffset, min_score: state.minScore,
  });
  if (state.lockId) params.set("lock_id", state.lockId);
  const data = await api("/api/pairing?" + params.toString());
  const box = $("#pairing-result");
  $("#reroll-btn").disabled = false;
  if (!data.pairing) {
    box.innerHTML = `<div class="empty">${esc(data.message || "No pairing found.")}</div>`;
    return;
  }
  const p = data.pairing;
  const terms = p.shared_terms || [];
  box.innerHTML = "";
  const grid = el("div", "pair-grid");
  grid.appendChild(pairCard(p.left, terms, "left"));
  const mid = el("div", "pair-mid", `<span class="x">×</span>`);
  grid.appendChild(mid);
  grid.appendChild(pairCard(p.right, terms, "right"));
  box.appendChild(grid);

  const why = el("div", "pair-why");
  why.innerHTML = `<b>Why paired:</b> ${esc(p.why)}`;
  box.appendChild(why);

  const shared = el("div", "shared");
  shared.innerHTML = `<span class="lbl">shared:</span>` +
    terms.map((t) => `<span class="term">${esc(t)}</span>`).join("");
  box.appendChild(shared);

  box.appendChild(el("div", "pair-meta",
    `Pairing ${p.offset + 1} of ${p.total_pairs} &middot; strength ${p.strength}` +
    (state.lockId ? " &middot; one article locked" : "")));
}

// ---------------------------------------------------------------- sources drawer
function openSources(open) {
  $("#sources-drawer").classList.toggle("open", open);
  $("#overlay").classList.toggle("show", open);
  if (open) loadSources();
}

async function loadSources() {
  const data = await api("/api/sources");
  const list = $("#sources-list");
  list.innerHTML = "";
  data.sources.forEach((s) => {
    const div = el("div", "src");
    div.innerHTML =
      `<div class="src-top">
         <div class="src-name"><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a>
           ${s.is_paywall ? `<span class="badge-paywall">PAYWALL</span>` : ""}</div>
         <span class="status ${s.status}">${s.status}</span>
       </div>
       <div class="src-meta">angle: ${esc(s.angle)}${s.type ? " &middot; " + esc(s.type) : ""}
         ${s.last_fetched ? " &middot; fetched " + fmtDate(s.last_fetched) : ""}</div>
       ${s.last_error ? `<div class="src-error">${esc(s.last_error)}</div>` : ""}
       <div class="src-actions">
         <button data-act="refetch">Re-fetch</button>
         <button data-act="toggle">${s.status === "disabled" ? "Enable" : "Disable"}</button>
         <button data-act="delete">Remove</button>
       </div>`;
    div.querySelector('[data-act="refetch"]').onclick = async () => {
      await api(`/api/sources/${s.id}/refetch`, { method: "POST" });
      toast("Re-fetching " + s.name + "…");
      setTimeout(() => { loadSources(); loadStats(); loadFeed(); }, 3000);
    };
    div.querySelector('[data-act="toggle"]').onclick = async () => {
      const next = s.status === "disabled" ? "active" : "disabled";
      await api(`/api/sources/${s.id}/status?status=${next}`, { method: "POST" });
      loadSources(); loadStats();
    };
    div.querySelector('[data-act="delete"]').onclick = async () => {
      if (!confirm("Remove " + s.name + "? Its articles stay until pruned.")) return;
      await api(`/api/sources/${s.id}`, { method: "DELETE" });
      loadSources(); loadStats();
    };
    list.appendChild(div);
  });
}

// ---------------------------------------------------------------- wiring
function init() {
  $("#min-score").addEventListener("input", (e) => {
    state.minScore = parseFloat(e.target.value);
    $("#min-score-val").textContent = state.minScore.toFixed(2);
  });
  $("#min-score").addEventListener("change", loadFeed);
  $("#include-seen").addEventListener("change", (e) => {
    state.includeSeen = e.target.checked; loadFeed();
  });

  let searchTimer;
  $("#search").addEventListener("input", (e) => {
    state.search = e.target.value.trim();
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadFeed, 250); // debounce
  });

  $("#saved-toggle").onclick = () => {
    state.savedOnly = !state.savedOnly;
    $("#saved-toggle").classList.toggle("active", state.savedOnly);
    loadFeed();
  };

  const applyDate = () => {
    $("#clear-date-btn").hidden = !state.date;
    $("#date-filter").value = state.date || "";
    loadDigest(); loadFeed();
  };
  $("#date-filter").addEventListener("change", (e) => {
    state.date = e.target.value || null; applyDate();
  });
  $("#today-btn").onclick = () => {
    state.date = new Date().toISOString().slice(0, 10); applyDate();
  };
  $("#clear-date-btn").onclick = () => { state.date = null; applyDate(); };

  $("#fetch-btn").onclick = async () => {
    await api("/api/fetch", { method: "POST" });
    toast("Fetch started — refreshing shortly…");
    setTimeout(() => { loadStats(); loadDates(); loadDigest(); loadFeed(); }, 5000);
  };

  $("#sources-btn").onclick = () => openSources(true);
  $("#close-sources").onclick = () => openSources(false);
  $("#overlay").onclick = () => openSources(false);

  const openPairing = () => {
    $("#pairing-panel").hidden = false;
    $("#pairing-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  };
  $("#pair-open").onclick = () => { openPairing(); state.pairOffset = 0; findPairing(); };
  $("#pair-close").onclick = () => { $("#pairing-panel").hidden = true; };

  document.querySelectorAll(".seg-btn").forEach((b) => {
    b.onclick = () => {
      document.querySelectorAll(".seg-btn").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      state.pairMode = b.dataset.mode;
      state.pairOffset = 0;
      findPairing();
    };
  });
  $("#pair-btn").onclick = () => { state.pairOffset = 0; findPairing(); };
  $("#reroll-btn").onclick = () => { state.pairOffset += 1; findPairing(); };

  $("#add-source-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = $("#new-url").value.trim();
    const angle = $("#new-angle").value;
    if (!url) return;
    try {
      await api("/api/sources", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, angle }),
      });
      $("#new-url").value = "";
      toast("Added — resolving feed & fetching…");
      loadSources();
      setTimeout(() => { loadSources(); loadStats(); loadFeed(); }, 4000);
    } catch (err) {
      toast("Error: " + err.message);
    }
  });

  loadStats();
  loadDates();
  loadFeed();
}

document.addEventListener("DOMContentLoaded", init);
