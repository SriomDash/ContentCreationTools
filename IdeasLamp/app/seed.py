"""Load sources.csv into the DB (idempotent — skips URLs already present)."""
from __future__ import annotations

import csv
import logging
import os
from urllib.parse import urlparse

from . import config
from .db import Repository
from .models import Source

log = logging.getLogger("ideaslamp.seed")

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources.csv")


def _name_from_url(url: str) -> str:
    net = urlparse(url).netloc.replace("www.", "")
    return net or url


def _is_paywall(notes: str) -> bool:
    low = (notes or "").lower()
    return any(flag in low for flag in config.PAYWALL_FLAGS)


def seed_sources(repo: Repository, csv_path: str = CSV_PATH) -> int:
    """Insert any CSV rows not already in the DB. Returns count inserted."""
    if not os.path.exists(csv_path):
        log.warning("sources.csv not found at %s", csv_path)
        return 0
    inserted = 0
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get("url") or "").strip()
            if not url or not url.lower().startswith("http"):
                continue
            if repo.get_source_by_url(url):
                continue
            angle = (row.get("angle") or "tech").strip().lower()
            notes = (row.get("notes") or "").strip()
            repo.add_source(Source(
                id=None, url=url, feed_url=None, name=_name_from_url(url),
                angle=angle, type=(row.get("type") or "").strip(), notes=notes,
                is_paywall=_is_paywall(notes), status="active",
            ))
            inserted += 1
    log.info("seed: inserted %d new sources from %s", inserted, csv_path)
    return inserted
