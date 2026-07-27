#!/usr/bin/env python3
"""
Creator's Story - a tiny local web app for entering creator data into a CSV.

Columns saved per row: Creator, Topic, Hook, Transcribe

Rules enforced:
  * Each save adds exactly ONE row (long transcribe stays in a single row).
  * You must add at least 5 rows for a creator before adding another creator.
  * A creator can have at most 10 rows. Once 10 are reached you must add a new creator.

Run:  python app.py
Then open the URL it prints (default http://127.0.0.1:8000).
No external packages required - standard library only.
"""

import csv
import io
import json
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "data.csv")
STATE_PATH = os.path.join(BASE_DIR, "state.json")
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

HEADER = ["Creator", "Topic", "Hook", "Transcribe"]

MIN_ROWS = 5   # rows required before another creator can be added
MAX_ROWS = 10  # hard cap of rows per creator

HOST = "127.0.0.1"
PORT = 8000


# --------------------------------------------------------------------------
# Storage helpers
# --------------------------------------------------------------------------
def ensure_csv():
    """Create the CSV with a header row if it does not exist yet."""
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(HEADER)


def read_rows():
    """Return list of data rows (dicts) from the CSV, excluding the header."""
    ensure_csv()
    rows = []
    with open(CSV_PATH, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if i == 0:
                continue  # skip header
            if not row:
                continue
            # pad short rows just in case
            row = (row + ["", "", "", ""])[:4]
            rows.append({
                "creator": row[0],
                "topic": row[1],
                "hook": row[2],
                "transcribe": row[3],
            })
    return rows


def one_line(text):
    """Collapse any line breaks and repeated whitespace into single spaces,
    so a field is stored as one physical line in the CSV file."""
    if text is None:
        return ""
    # normalise all newline styles, then squeeze runs of whitespace to one space
    return " ".join(text.split())


def append_row(creator, topic, hook, transcribe):
    """Append one row to the CSV using proper quoting so it stays a single record."""
    ensure_csv()
    with open(CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow([one_line(creator), one_line(topic),
                         one_line(hook), one_line(transcribe)])


def load_state():
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"current_creator": None}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f)


def count_rows_for(creator):
    if not creator:
        return 0
    return sum(1 for r in read_rows() if r["creator"] == creator)


def build_status():
    """Compute the current status the UI needs to enforce all rules."""
    state = load_state()
    current = state.get("current_creator")
    count = count_rows_for(current)

    if current is None:
        # No creator yet -> must create the first one.
        can_add_creator = True
        can_add_row = False
    else:
        can_add_creator = count >= MIN_ROWS
        can_add_row = count < MAX_ROWS

    # list of creators (in order of first appearance) with their row counts
    order = []
    counts = {}
    for r in read_rows():
        c = r["creator"]
        if c not in counts:
            counts[c] = 0
            order.append(c)
        counts[c] += 1
    creators = [{"name": c, "count": counts[c]} for c in order]

    return {
        "current_creator": current,
        "count": count,
        "min_rows": MIN_ROWS,
        "max_rows": MAX_ROWS,
        "can_add_creator": can_add_creator,
        "can_add_row": can_add_row,
        "remaining_to_min": max(0, MIN_ROWS - count) if current else MIN_ROWS,
        "creators": creators,
    }


# --------------------------------------------------------------------------
# HTTP handler
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep the console quiet

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    # ---- GET ----
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._serve_index()
        elif self.path == "/api/status":
            self._send_json(build_status())
        else:
            self.send_error(404, "Not found")

    def _serve_index(self):
        try:
            with open(INDEX_PATH, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            self.send_error(500, "index.html is missing")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---- POST ----
    def do_POST(self):
        try:
            if self.path == "/api/creator":
                self._add_creator()
            elif self.path == "/api/row":
                self._add_row()
            else:
                self.send_error(404, "Not found")
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, code=400)

    def _add_creator(self):
        data = self._read_json()
        name = (data.get("name") or "").strip()
        if not name:
            self._send_json({"ok": False, "error": "Creator name is required."}, 400)
            return

        state = load_state()
        current = state.get("current_creator")
        if current is not None:
            count = count_rows_for(current)
            if count < MIN_ROWS:
                self._send_json({
                    "ok": False,
                    "error": f"You need at least {MIN_ROWS} rows for '{current}' "
                             f"before adding a new creator (currently {count})."
                }, 400)
                return

        state["current_creator"] = name
        save_state(state)
        self._send_json({"ok": True, "status": build_status()})

    def _add_row(self):
        data = self._read_json()
        state = load_state()
        creator = state.get("current_creator")
        if not creator:
            self._send_json({"ok": False, "error": "Add a creator first."}, 400)
            return

        count = count_rows_for(creator)
        if count >= MAX_ROWS:
            self._send_json({
                "ok": False,
                "error": f"'{creator}' already has {MAX_ROWS} rows. Add another creator."
            }, 400)
            return

        topic = (data.get("topic") or "").strip()
        hook = (data.get("hook") or "").strip()
        transcribe = (data.get("transcribe") or "").strip()

        if not topic and not hook and not transcribe:
            self._send_json({"ok": False, "error": "Please fill in at least one field."}, 400)
            return

        append_row(creator, topic, hook, transcribe)
        self._send_json({"ok": True, "status": build_status()})


# --------------------------------------------------------------------------
def main():
    ensure_csv()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f"http://{HOST}:{PORT}"
    print("=" * 60)
    print("  Creator's Story is running.")
    print(f"  Open this in your browser:  {url}")
    print(f"  Data is saved to:           {CSV_PATH}")
    print("  Press Ctrl+C here to stop the app.")
    print("=" * 60)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping. Goodbye!")
        server.shutdown()


if __name__ == "__main__":
    main()
