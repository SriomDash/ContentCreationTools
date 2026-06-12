/* GridRank — Excel export. Adds an "Export Excel" button to the actions row.
   Reads posts the panel already collected (window.__IGFS_GET_POSTS), respects
   the visible date filters, ranks by a Views+Likes heat score, stars top 2,
   links are clickable. Pure client-side via bundled SheetJS. */
(function () {
  "use strict";

  function num(v) {
    if (typeof v === "number" && isFinite(v)) return v;
    if (typeof v === "string") {
      var s = v.trim().toLowerCase().replace(/,/g, "");
      var m = s.match(/^([\d.]+)\s*([kmb])?$/);
      if (m) { var mult = m[2] === "k" ? 1e3 : m[2] === "m" ? 1e6 : m[2] === "b" ? 1e9 : 1; return Math.round(parseFloat(m[1]) * mult); }
      var d = parseInt(s.replace(/[^\d]/g, ""), 10); return isFinite(d) ? d : 0;
    }
    return 0;
  }
  function dateOf(p) { return p.taken_at ? new Date(p.taken_at * 1000) : null; }
  function fmtDate(d) { return d ? d.toISOString().slice(0, 10) : ""; }
  function cap(p) { return String(p.caption || "").replace(/\s+/g, " ").trim(); }
  function creatorOf(rows) {
    for (var i = 0; i < rows.length; i++) if (rows[i].owner) return rows[i].owner;
    return (location.pathname.split("/").filter(Boolean)[0] || "creator");
  }
  function activeDates() {
    var root = document.getElementById("igfs-panel");
    var dEls = root ? root.querySelectorAll('input[type="date"]') : [];
    var from = dEls[0] && dEls[0].value ? new Date(dEls[0].value) : null;
    var to = dEls[1] && dEls[1].value ? new Date(dEls[1].value) : null;
    if (to) to.setHours(23, 59, 59, 999);
    return { from: from, to: to };
  }

  function build() {
    var all = (window.__IGFS_GET_POSTS ? window.__IGFS_GET_POSTS() : []);
    all = all.filter(function (p) { return p.media_type === "video" || num(p.views) > 0; });
    var r = activeDates();
    if (r.from || r.to) {
      all = all.filter(function (p) {
        var d = dateOf(p); if (!d) return false;
        if (r.from && d < r.from) return false;
        if (r.to && d > r.to) return false;
        return true;
      });
    }
    if (!all.length) return { rows: [], range: r, basis: "none" };
    // Decide ranking basis: use views only if a meaningful share of posts have them.
    var withViews = all.filter(function (p) { return num(p.views) > 0; }).length;
    var useViews = withViews >= Math.max(2, all.length * 0.3);
    var vMax = Math.max.apply(null, all.map(function (p) { return num(p.views); })) || 1;
    var lMax = Math.max.apply(null, all.map(function (p) { return num(p.likes); })) || 1;
    var rows = all.map(function (p) {
      var v = num(p.views), l = num(p.likes), c = num(p.comments), d = dateOf(p);
      var heat = useViews
        ? ((v / vMax * 100) + (l / lMax * 100)) / 2   // both engines
        : (l / lMax * 100);                            // likes-only fallback
      return { owner: p.owner, caption: cap(p), views: v, likes: l, comments: c,
        eng: v > 0 ? +((l + c) / v * 100).toFixed(2) : "", posted: fmtDate(d),
        heat: +heat.toFixed(1), url: p.url || "" };
    });
    rows.sort(function (a, b) { return b.heat - a.heat; });
    return { rows: rows, range: r, basis: useViews ? "views+likes" : "likes-only" };
  }

  function exportExcel() {
    if (typeof XLSX === "undefined") { alert("Export library missing."); return; }
    var built = build();
    if (!built.rows.length) {
      alert("No videos collected for this filter yet.\nScroll the creator's Reels/grid, set your date range, then export.");
      return;
    }
    var creator = creatorOf(built.rows);
    var r = built.range;
    var label = (r.from ? fmtDate(r.from) : "all") + "_to_" + (r.to ? fmtDate(r.to) : "now");

    var aoa = [
      ["GridRank export — viral content research"],
      ["Creator", creator],
      ["Date range", (r.from ? fmtDate(r.from) : "(open)") + "  ->  " + (r.to ? fmtDate(r.to) : "(open)")],
      ["Exported", new Date().toISOString().slice(0, 16).replace("T", " ")],
      ["Ranked by", built.basis === "views+likes"
        ? "Heat = avg(normalized views, normalized likes), high to low"
        : "Heat = normalized likes (views not available from grid), high to low"],
      ["Basis", built.basis],
      [],
      ["Rank", "Heat", "Views", "Likes", "Comments", "Eng %", "Posted", "Caption", "Link"]
    ];
    var headerRow = aoa.length - 1;
    built.rows.forEach(function (row, i) {
      aoa.push([i + 1, row.heat, row.views, row.likes, row.comments, row.eng, row.posted, row.caption, row.url]);
    });

    var ws = XLSX.utils.aoa_to_sheet(aoa);
    ws["!cols"] = [{ wch: 6 }, { wch: 8 }, { wch: 11 }, { wch: 10 }, { wch: 10 }, { wch: 8 }, { wch: 11 }, { wch: 60 }, { wch: 42 }];
    var first = headerRow + 1;
    built.rows.forEach(function (row, i) {
      var er = first + i + 1;
      if (row.url && ws["I" + er]) ws["I" + er].l = { Target: row.url, Tooltip: "Open on Instagram" };
      if (i < 2 && ws["A" + er]) ws["A" + er].v = "\u2605 " + ws["A" + er].v;
    });

    var wb = XLSX.utils.book_new();
    var safe = creator.replace(/[^a-z0-9_-]/gi, "").slice(0, 20) || "creator";
    XLSX.utils.book_append_sheet(wb, ws, safe.slice(0, 31));
    XLSX.writeFile(wb, "gridrank_" + safe + "_" + label + ".xlsx");
  }

  // inject button into the panel's actions row
  function inject() {
    var actions = document.querySelector("#igfs-panel .igfs-actions");
    if (!actions || actions.querySelector(".igfs-export-btn")) return;
    var b = document.createElement("button");
    b.className = "igfs-export-btn";
    b.type = "button";
    b.textContent = "\u2B07 Export Excel";
    b.title = "Download this creator's videos (current date range) ranked by views + likes";
    b.addEventListener("click", exportExcel);
    actions.appendChild(b);
  }
  setInterval(inject, 1500);
})();
