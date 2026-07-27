"""
ingest.py — the pipeline.

  auth (read-only) -> list messages under ONE label within the SINCE_DAYS window
  -> for each message: read sender/subject/date + HTML body
  -> KEEP every newsletter
  -> extract + clean + dedupe links
  -> two-gate flag + relevance score
  -> store in SQLite (seen flag preserved across runs)

Run:  python ingest.py            (uses config.LABEL / config.SINCE_DAYS)
      python ingest.py --days 5   (override the window for one run)
      python ingest.py --label "My Label"

READ-ONLY: this only ever calls messages.list / messages.get. It never modifies,
labels, marks-read, archives, deletes, or sends anything in Gmail.
"""

import argparse
import logging
import time

import config
import db
from auth import get_service
from extract import get_html_body, extract_links
from classify import classify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("digest")


def resolve_label_id(service, label_name):
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    match = next((l["id"] for l in labels if l["name"] == label_name), None)
    if not match:
        log.error('Label "%s" not found. Available labels:', label_name)
        for l in sorted(labels, key=lambda x: x["name"].lower()):
            log.error("    %s", l["name"])
        log.error('Set LABEL in config.py to one of the names above.')
    return match


def list_message_ids(service, label_id, days):
    """All message ids under the label within the window (handles paging)."""
    ids = []
    query = f"newer_than:{days}d"
    page_token = None
    while True:
        resp = service.users().messages().list(
            userId="me", labelIds=[label_id], q=query,
            maxResults=100, pageToken=page_token,
        ).execute()
        ids.extend(m["id"] for m in resp.get("messages", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids


def _header(headers, name):
    return next((h["value"] for h in headers if h["name"].lower() == name.lower()), "")


def run(label_name=None, days=None):
    label_name = label_name or config.LABEL
    days = days if days is not None else config.SINCE_DAYS

    db.init_db(config.DB_PATH)
    service = get_service()

    label_id = resolve_label_id(service, label_name)
    if not label_id:
        return

    msg_ids = list_message_ids(service, label_id, days)
    log.info('Scanning label "%s" (last %d days): %d newsletters found.',
             label_name, days, len(msg_ids))

    now = int(time.time())
    total_links = 0
    total_flagged = 0
    total_boilerplate = 0

    with db.connect(config.DB_PATH) as conn:
        for mid in msg_ids:
            full = service.users().messages().get(
                userId="me", id=mid, format="full",
            ).execute()
            headers = full.get("payload", {}).get("headers", [])
            sender = _header(headers, "From")
            subject = _header(headers, "Subject") or "(no subject)"
            received_at = int(full.get("internalDate", "0")) // 1000

            db.upsert_message(
                conn, id=mid, sender=sender, subject=subject,
                received_at=received_at, label=label_name, created_at=now,
            )

            html = get_html_body(full.get("payload", {}))
            links = extract_links(html)

            flagged_here = 0
            for link in links:
                c = classify(link["url"], link["anchor_text"], link["snippet"])
                if not c["is_article"]:
                    total_boilerplate += 1
                if c["is_ai"]:
                    flagged_here += 1
                db.upsert_link(
                    conn,
                    message_id=mid,
                    url=link["url"],
                    anchor_text=link["anchor_text"],
                    snippet=link["snippet"][:500],
                    is_article=c["is_article"],
                    is_ai=c["is_ai"],
                    score=c["score"],
                    matched=", ".join(c["matched"]),
                )
            total_links += len(links)
            total_flagged += flagged_here
            log.info('  %-55s  %2d links, %2d tech/AI',
                     (subject[:52] + "...") if len(subject) > 55 else subject,
                     len(links), flagged_here)

    log.info("Done. %d newsletters scanned, %d links extracted "
             "(%d boilerplate), %d flagged tech/AI.",
             len(msg_ids), total_links, total_boilerplate, total_flagged)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Scan a Gmail label and build the digest DB (read-only).")
    ap.add_argument("--label", default=None, help="Gmail label to scan (default: config.LABEL)")
    ap.add_argument("--days", type=int, default=None, help="Look-back window in days (default: config.SINCE_DAYS)")
    args = ap.parse_args()
    run(label_name=args.label, days=args.days)
