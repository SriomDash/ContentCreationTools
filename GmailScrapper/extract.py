"""
extract.py — pull the HTML body out of a Gmail message and extract clean links.

Responsibilities:
  * decode the message's HTML body (falls back to text/plain)
  * find all <a href> links + their anchor text + a surrounding text snippet
  * clean each URL:
      - unwrap common click-tracking / redirect wrappers so we store the REAL
        destination article URL where possible
      - strip utm_* and other tracking query params
      - normalize for dedupe
  * dedupe within a message (later, ingest dedupes across messages via the DB)

Pure parsing/String work — no network calls, nothing leaves the machine.
"""

import base64
import re
from urllib.parse import (
    urlparse, urlunparse, parse_qsl, urlencode, unquote, parse_qs,
)
from bs4 import BeautifulSoup

# Query params stripped from every URL (tracking / analytics noise).
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_name", "utm_brand", "mc_cid", "mc_eid", "mkt_tok",
    "ref", "ref_src", "fbclid", "gclid", "igshid", "vero_id", "vero_conv",
    "ck_subscriber_id", "_bhlid", "_hsenc", "_hsmi", "hsctatracking",
    "spm", "yclid", "wickedid", "cmpid",
}

# Hosts that wrap the real URL as a query param (e.g. ?url=... / ?u=...).
# We unwrap the first param that decodes to an http(s) URL.
_REDIRECT_QUERY_KEYS = ("url", "u", "redirect", "redirect_url", "target",
                        "destination", "dest", "link", "l", "r")

# Path-segment based redirectors (link.example.com/ss/c/<blob>/<encoded-url>).
# For these we scan path segments and query values for an embedded http(s) URL.
_REDIRECT_HOST_HINTS = (
    "click", "clicks", "email", "mail", "track", "tracking", "link", "links",
    "e.customeriomail", "sendgrid", "list-manage", "mailchimp", "cmail",
    "beehiiv", "substack.com/redirect", "convertkit", "ck.page", "sparkloop",
    "hubspotlinks", "mandrillapp", "sg-links", "engage",
)


def get_html_body(payload):
    """Walk a Gmail message payload and return the best HTML (or text) body."""
    html, text = _walk_parts(payload)
    return html or text or ""


def _walk_parts(part):
    html, text = None, None
    mime = part.get("mimeType", "")
    body = part.get("body", {})
    data = body.get("data")

    if data:
        decoded = _b64(data)
        if mime == "text/html" and html is None:
            html = decoded
        elif mime == "text/plain" and text is None:
            text = decoded

    for sub in part.get("parts", []) or []:
        h, t = _walk_parts(sub)
        html = html or h
        text = text or t
    return html, text


def _b64(data):
    try:
        return base64.urlsafe_b64decode(data.encode("utf-8")).decode(
            "utf-8", errors="replace")
    except Exception:
        return ""


def extract_links(html):
    """Return a list of dicts: {url, anchor_text, snippet} deduped by clean URL.

    If `html` is actually plain text (no tags), we regex out bare URLs.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=True)

    results = []
    seen = set()

    if anchors:
        for a in anchors:
            raw = a["href"].strip()
            if not raw or raw.startswith(("#", "mailto:", "tel:", "javascript:")):
                # keep mailto out of article space; anchors/js are useless
                if raw.startswith("mailto:"):
                    url = raw  # store as-is; classify will mark non-article
                else:
                    continue
            else:
                url = clean_url(raw)
            if not url:
                continue

            anchor_text = _collapse_ws(a.get_text(" ", strip=True))
            snippet = _snippet_around(a)

            key = url.lower()
            if key in seen:
                # merge: prefer a longer anchor text / snippet if we had blanks
                continue
            seen.add(key)
            results.append({"url": url, "anchor_text": anchor_text,
                            "snippet": snippet})
    else:
        # plain-text fallback
        for m in re.finditer(r"https?://[^\s<>()\"']+", html):
            url = clean_url(m.group(0))
            if not url:
                continue
            key = url.lower()
            if key in seen:
                continue
            seen.add(key)
            start = max(0, m.start() - 120)
            snippet = _collapse_ws(html[start:m.end() + 120])
            results.append({"url": url, "anchor_text": url, "snippet": snippet})

    return results


def _snippet_around(a, radius=160):
    """Grab nearby visible text so topical matching has context beyond the anchor."""
    parts = [a.get_text(" ", strip=True)]
    parent = a.find_parent(["p", "td", "li", "div", "span", "h1", "h2", "h3"])
    if parent:
        parts.append(parent.get_text(" ", strip=True))
    text = _collapse_ws(" ".join(p for p in parts if p))
    return text[:radius * 2]


def _collapse_ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


def clean_url(raw):
    """Unwrap redirects and strip tracking params. Returns "" if unusable."""
    if not raw:
        return ""
    raw = raw.strip()
    if raw.startswith("mailto:"):
        return raw
    if not raw.lower().startswith(("http://", "https://")):
        return ""

    url = _unwrap_redirect(raw)
    url = _strip_tracking(url)
    return url


def _unwrap_redirect(url, depth=0):
    """If the URL is a click-tracking wrapper, return the embedded destination.

    Best-effort and bounded: handles ?url=<encoded>, ?u=<encoded>, and encoded
    http(s) URLs embedded in the path of known redirector hosts.
    """
    if depth > 4:
        return url
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    # 1) query-param wrappers (works on any host)
    qs = parse_qs(parsed.query)
    for key in _REDIRECT_QUERY_KEYS:
        for val in qs.get(key, []):
            cand = _as_http(unquote(val))
            if cand and cand != url:
                return _unwrap_redirect(cand, depth + 1)

    # 2) path-embedded encoded URLs on redirector-looking hosts
    if any(h in host for h in _REDIRECT_HOST_HINTS) or "redirect" in parsed.path.lower():
        embedded = _find_embedded_http(parsed.path) or _find_embedded_http(parsed.query)
        if embedded and embedded != url:
            return _unwrap_redirect(embedded, depth + 1)

    return url


def _as_http(s):
    s = (s or "").strip()
    if s.lower().startswith(("http://", "https://")):
        return s
    return None


def _find_embedded_http(blob):
    """Find an http(s) URL embedded (possibly %-encoded) in a path/query blob."""
    if not blob:
        return None
    dec = unquote(blob)
    m = re.search(r"https?://[^\s]+", dec)
    if m:
        return m.group(0).rstrip("/")
    return None


def _strip_tracking(url):
    parsed = urlparse(url)
    kept = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False)
            if k.lower() not in _TRACKING_PARAMS and not k.lower().startswith("utm_")]
    query = urlencode(kept)
    # normalize: drop fragment, drop trailing slash on path (keep root "/")
    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    cleaned = urlunparse((parsed.scheme, parsed.netloc, path, parsed.params,
                          query, ""))
    return cleaned
