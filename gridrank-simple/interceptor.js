// interceptor.js — runs in the page's MAIN world.
// Makes NO extra network requests. It only reads the JSON that Instagram
// itself loads while you browse, pulls post metrics, and forwards them to
// the panel (ISOLATED world) via a window CustomEvent.

(function () {
  "use strict";
  var EVENT_NAME = "__IGFS_POSTS__";

  function num(v) {
    return typeof v === "number" && isFinite(v) ? v : 0;
  }

  // Walk an arbitrary JSON object and collect anything that looks like a media node.
  function harvest(obj, out, depth) {
    if (!obj || typeof obj !== "object" || depth > 8) return;
    if (Array.isArray(obj)) {
      for (var i = 0; i < obj.length; i++) harvest(obj[i], out, depth + 1);
      return;
    }
    // A media node usually has a shortcode/code and some counts.
    var code = obj.code || obj.shortcode;
    var hasCounts =
      "like_count" in obj || "comment_count" in obj ||
      "play_count" in obj || "view_count" in obj ||
      "edge_media_preview_like" in obj || "edge_liked_by" in obj;

    if (code && hasCounts) {
      var caption = "";
      try {
        if (typeof obj.caption === "string") caption = obj.caption;
        else if (obj.caption && obj.caption.text) caption = obj.caption.text;
        else if (obj.edge_media_to_caption && obj.edge_media_to_caption.edges &&
                 obj.edge_media_to_caption.edges[0]) {
          caption = obj.edge_media_to_caption.edges[0].node.text || "";
        }
      } catch (e) {}

      var likes = num(obj.like_count);
      if (!likes && obj.edge_media_preview_like) likes = num(obj.edge_media_preview_like.count);
      if (!likes && obj.edge_liked_by) likes = num(obj.edge_liked_by.count);

      var comments = num(obj.comment_count);
      if (!comments && obj.edge_media_to_comment) comments = num(obj.edge_media_to_comment.count);
      if (!comments && obj.edge_media_to_parent_comment) comments = num(obj.edge_media_to_parent_comment.count);

      var views = num(obj.play_count) || num(obj.view_count) ||
                  num(obj.video_view_count) || num(obj.video_play_count) ||
                  num(obj.ig_play_count) || num(obj.fb_play_count) ||
                  (obj.media && (num(obj.media.play_count) || num(obj.media.view_count))) ||
                  num(obj.reshare_count_disabled ? 0 : obj.play_count_reel);

      var owner = "";
      try { owner = (obj.user && obj.user.username) || (obj.owner && obj.owner.username) || ""; }
      catch (e) {}

      var taken = obj.taken_at || obj.taken_at_timestamp || 0;

      var mtype = obj.media_type; // 2 = video on IG; product_type "clips" = reel
      var isVideo = mtype === 2 || obj.is_video === true ||
                    (obj.product_type && /clip|igtv|reel/i.test(obj.product_type)) ||
                    views > 0;

      out.push({
        id: obj.id || code,
        shortcode: code,
        url: "https://www.instagram.com/" + ((obj.product_type && /clip/i.test(obj.product_type)) ? "reel" : "p") + "/" + code + "/",
        caption: caption,
        likes: likes,
        comments: comments,
        views: views,
        owner: owner,
        taken_at: taken ? num(taken) : 0,
        media_type: isVideo ? "video" : "image"
      });
    }

    // keep walking
    for (var k in obj) {
      if (Object.prototype.hasOwnProperty.call(obj, k)) {
        var val = obj[k];
        if (val && typeof val === "object") harvest(val, out, depth + 1);
      }
    }
  }

  function emit(jsonText) {
    try {
      var data = JSON.parse(jsonText);
      var found = [];
      harvest(data, found, 0);
      if (found.length) {
        window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: found }));
      }
    } catch (e) { /* not JSON, ignore */ }
  }

  // ---- hook fetch ----
  var origFetch = window.fetch;
  if (origFetch) {
    window.fetch = function () {
      return origFetch.apply(this, arguments).then(function (res) {
        try {
          var ct = res.headers.get("content-type") || "";
          if (ct.indexOf("application/json") > -1) {
            res.clone().text().then(emit).catch(function () {});
          }
        } catch (e) {}
        return res;
      });
    };
  }

  // ---- hook XMLHttpRequest ----
  var origOpen = XMLHttpRequest.prototype.open;
  var origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.__igfs_url = url;
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function () {
    var xhr = this;
    this.addEventListener("load", function () {
      try {
        var ct = xhr.getResponseHeader("content-type") || "";
        if (ct.indexOf("application/json") > -1 && typeof xhr.responseText === "string") {
          emit(xhr.responseText);
        }
      } catch (e) {}
    });
    return origSend.apply(this, arguments);
  };
})();
