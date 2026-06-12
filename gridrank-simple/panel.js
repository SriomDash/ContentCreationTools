// panel.js — ISOLATED world. Builds the sortable side panel.
// All features free. Listens to interceptor events, dedupes, sorts, filters.

(function () {
  "use strict";
  var EVENT_NAME = "__IGFS_POSTS__";

  var posts = {};          // key -> record (deduped, enriched over time)
  var sortKey = "views";   // views | likes | comments
  var root, listEl, countEl;
  var renderQueued = false;

  // expose collected posts for the export module
  window.__IGFS_GET_POSTS = function () {
    return Object.keys(posts).map(function (k) { return posts[k]; });
  };
  window.__IGFS_GET_SORTKEY = function () { return sortKey; };

  /* ---------- ingest ---------- */
  window.addEventListener(EVENT_NAME, function (e) {
    var batch = (e && e.detail) || [];
    if (!Array.isArray(batch)) batch = [batch];
    var changed = false;
    batch.forEach(function (p) {
      if (!p) return;
      var key = p.url || p.id || p.shortcode;
      if (!key) return;
      var prev = posts[key] || {};
      // keep the max of each metric we've ever seen (counts only grow / fill in)
      posts[key] = {
        id: p.id || prev.id,
        shortcode: p.shortcode || prev.shortcode,
        url: p.url || prev.url,
        caption: p.caption || prev.caption || "",
        likes: Math.max(p.likes || 0, prev.likes || 0),
        comments: Math.max(p.comments || 0, prev.comments || 0),
        views: Math.max(p.views || 0, prev.views || 0),
        owner: p.owner || prev.owner || "",
        taken_at: p.taken_at || prev.taken_at || 0,
        media_type: p.media_type || prev.media_type || "image"
      };
      changed = true;
    });
    if (changed) queueRender();
  });

  function queueRender() {
    if (renderQueued) return;
    renderQueued = true;
    setTimeout(function () { renderQueued = false; render(); }, 250);
  }

  /* ---------- helpers ---------- */
  function fmt(n) {
    n = n || 0;
    if (n >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, "") + "B";
    if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
    if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
    return String(n);
  }
  function parseShort(s) {
    if (!s) return null;
    s = String(s).trim().toLowerCase().replace(/,/g, "");
    var m = s.match(/^([\d.]+)\s*([kmb])?$/);
    if (!m) { var d = parseInt(s.replace(/[^\d]/g, ""), 10); return isFinite(d) ? d : null; }
    var mult = m[2] === "k" ? 1e3 : m[2] === "m" ? 1e6 : m[2] === "b" ? 1e9 : 1;
    return Math.round(parseFloat(m[1]) * mult);
  }
  function dateOf(p) { return p.taken_at ? new Date(p.taken_at * 1000) : null; }

  function currentFilters() {
    var minV = parseShort(root.querySelector("#igfs-min") && root.querySelector("#igfs-min").value);
    var maxV = parseShort(root.querySelector("#igfs-max") && root.querySelector("#igfs-max").value);
    var dEls = root.querySelectorAll('input[type="date"]');
    var from = dEls[0] && dEls[0].value ? new Date(dEls[0].value) : null;
    var to = dEls[1] && dEls[1].value ? new Date(dEls[1].value) : null;
    if (to) to.setHours(23, 59, 59, 999);
    return { minV: minV, maxV: maxV, from: from, to: to };
  }

  function applyFilters(arr) {
    var f = currentFilters();
    return arr.filter(function (p) {
      var val = p[sortKey] || 0;
      if (f.minV != null && val < f.minV) return false;
      if (f.maxV != null && val > f.maxV) return false;
      if (f.from || f.to) {
        var d = dateOf(p);
        if (!d) return false;
        if (f.from && d < f.from) return false;
        if (f.to && d > f.to) return false;
      }
      return true;
    });
  }

  /* ---------- render ---------- */
  function render() {
    if (!listEl) return;
    var arr = Object.keys(posts).map(function (k) { return posts[k]; });
    arr = applyFilters(arr);
    arr.sort(function (a, b) { return (b[sortKey] || 0) - (a[sortKey] || 0); });

    countEl.textContent = arr.length + " posts";
    if (!arr.length) {
      listEl.innerHTML =
        '<div class="igfs-empty">No posts match yet.<br>Open a creator\u2019s profile and scroll their grid or Reels, then adjust filters.</div>';
      return;
    }

    var html = "";
    arr.forEach(function (p, i) {
      var d = dateOf(p);
      var ds = d ? d.toISOString().slice(0, 10) : "";
      var star = i < 2 ? '<span class="igfs-star" title="top performer">\u2605</span>' : "";
      html +=
        '<a class="igfs-item" href="' + p.url + '" target="_blank" rel="noopener">' +
          '<span class="igfs-rank">' + star + (i + 1) + '</span>' +
          '<span class="igfs-meta">' +
            '<span class="igfs-stats">' +
              '<span title="views">\u25B6 ' + fmt(p.views) + '</span>' +
              '<span title="likes">\u2665 ' + fmt(p.likes) + '</span>' +
              '<span title="comments">\u{1F4AC} ' + fmt(p.comments) + '</span>' +
            '</span>' +
            '<span class="igfs-cap">' + (ds ? ds + " · " : "") + escapeHtml(p.caption || "(no caption)") + '</span>' +
          '</span>' +
        '</a>';
    });
    listEl.innerHTML = html;
  }

  function escapeHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  /* ---------- build the UI ---------- */
  function build() {
    if (document.getElementById("igfs-panel")) return;

    root = document.createElement("div");
    root.id = "igfs-panel";
    root.className = "igfs-panel";
    root.innerHTML =
      '<div class="igfs-header">' +
        '<span class="igfs-title">GridRank</span>' +
        '<span class="igfs-count" id="igfs-count">0 posts</span>' +
        '<button class="igfs-collapse" title="hide/show">\u2013</button>' +
      '</div>' +
      '<div class="igfs-body">' +
        '<div class="igfs-sortrow">' +
          '<button class="igfs-sort on" data-k="views">Most Views</button>' +
          '<button class="igfs-sort" data-k="likes">Most Likes</button>' +
          '<button class="igfs-sort" data-k="comments">Most Comments</button>' +
        '</div>' +
        '<div class="igfs-filters">' +
          '<div class="igfs-frow">' +
            '<span class="igfs-flabel" id="igfs-rangelabel">Views range</span>' +
            '<input type="text" id="igfs-min" placeholder="min e.g 10k">' +
            '<span class="igfs-fdash">\u2013</span>' +
            '<input type="text" id="igfs-max" placeholder="max e.g 2m">' +
          '</div>' +
          '<div class="igfs-frow">' +
            '<span class="igfs-flabel">Posted</span>' +
            '<input type="date">' +
            '<span class="igfs-fdash">\u2013</span>' +
            '<input type="date">' +
          '</div>' +
          '<button class="igfs-fclear">Clear filters</button>' +
        '</div>' +
        '<div class="igfs-actions"></div>' +
        '<div class="igfs-list" id="igfs-list"></div>' +
      '</div>';
    document.body.appendChild(root);

    listEl = root.querySelector("#igfs-list");
    countEl = root.querySelector("#igfs-count");

    // sort buttons
    root.querySelectorAll(".igfs-sort").forEach(function (b) {
      b.addEventListener("click", function () {
        root.querySelectorAll(".igfs-sort").forEach(function (x) { x.classList.remove("on"); });
        b.classList.add("on");
        sortKey = b.dataset.k;
        var lbl = root.querySelector("#igfs-rangelabel");
        lbl.textContent = (sortKey === "views" ? "Views" : sortKey === "likes" ? "Likes" : "Comments") + " range";
        render();
      });
    });
    // filters re-render live
    root.querySelectorAll(".igfs-filters input").forEach(function (inp) {
      inp.addEventListener("input", render);
      inp.addEventListener("change", render);
    });
    root.querySelector(".igfs-fclear").addEventListener("click", function () {
      root.querySelectorAll(".igfs-filters input").forEach(function (i) { i.value = ""; });
      render();
    });
    // collapse
    root.querySelector(".igfs-collapse").addEventListener("click", function () {
      root.classList.toggle("igfs-min");
      this.textContent = root.classList.contains("igfs-min") ? "+" : "\u2013";
    });

    render();
  }

  // build once DOM is ready, and re-assert if IG nukes it on navigation
  function ensure() { if (!document.getElementById("igfs-panel")) build(); }
  if (document.body) build(); else document.addEventListener("DOMContentLoaded", build);
  setInterval(ensure, 2000);
})();
