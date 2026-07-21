"""
Background scheduler. Three jobs:

  1. Interval fetch      — every `fetch_interval_hours` (default 3h), keeps the
                           feed fresh through the day.
  2. Nightly digest      — once a night, fetches then logs a topic digest of
                           everything posted that day (angles + top keywords).
  3. Retention cleanup   — once a day, deletes articles older than
                           `retention_days` (default 10) so the DB stays small.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from . import config, ingest
from .db import Repository
from .digest import daily_digest, format_digest_line

log = logging.getLogger("ideaslamp.scheduler")

_scheduler: BackgroundScheduler | None = None


def run_nightly_digest(repo: Repository) -> dict:
    """Fetch, then compute + log the topic digest for today."""
    log.info("nightly job: fetching before digest...")
    ingest.fetch_all(repo)
    d = daily_digest(repo)
    log.info(format_digest_line(d))
    return d


def run_retention_cleanup(repo: Repository) -> int:
    """Delete articles older than the retention window."""
    days = config.SETTINGS["retention_days"]
    deleted = repo.delete_articles_older_than(days)
    log.info("retention cleanup: deleted %d articles older than %d days", deleted, days)
    return deleted


def start_scheduler(repo: Repository) -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    s = config.SETTINGS
    sched = BackgroundScheduler(daemon=True)

    # 1. Interval fetch (keeps the feed fresh).
    sched.add_job(
        lambda: ingest.fetch_all(repo),
        trigger=IntervalTrigger(hours=s["fetch_interval_hours"]),
        id="fetch_all", max_instances=1, coalesce=True,
    )

    # 2. Nightly fetch + topic digest.
    sched.add_job(
        lambda: run_nightly_digest(repo),
        trigger=CronTrigger(hour=s["nightly_digest_hour"], minute=s["nightly_digest_minute"]),
        id="nightly_digest", max_instances=1, coalesce=True,
    )

    # 3. Daily retention cleanup.
    sched.add_job(
        lambda: run_retention_cleanup(repo),
        trigger=CronTrigger(hour=s["retention_cleanup_hour"], minute=s["retention_cleanup_minute"]),
        id="retention_cleanup", max_instances=1, coalesce=True,
    )

    sched.start()
    log.info("scheduler started: interval-fetch every %.2fh | nightly digest %02d:%02d | "
             "retention cleanup %02d:%02d (keep %d days)",
             s["fetch_interval_hours"], s["nightly_digest_hour"], s["nightly_digest_minute"],
             s["retention_cleanup_hour"], s["retention_cleanup_minute"], s["retention_days"])
    _scheduler = sched
    return sched


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
