"""Plain dataclasses for the domain objects. No DB/logic coupling here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Source:
    id: Optional[int]
    url: str
    feed_url: Optional[str]
    name: str
    angle: str
    type: str = ""
    notes: str = ""
    is_paywall: bool = False
    status: str = "active"  # active | blocked | no_feed | disabled
    last_fetched: Optional[str] = None
    last_error: Optional[str] = None


@dataclass
class Article:
    id: Optional[int]
    canonical_url: str
    title: str
    summary: str
    source_id: int
    published_at: Optional[str]
    score: float = 0.0
    passed_topic_gate: bool = False
    primary_angle: str = "tech"
    angles: List[str] = field(default_factory=list)
    is_critic: bool = False
    fingerprint: List[str] = field(default_factory=list)
    seen: bool = False
    starred: bool = False
    created_at: Optional[str] = None
    # Joined-in for display convenience (not stored on the articles table):
    source_name: Optional[str] = None
