"""Append-only JSONL audit log -- the system's source of truth.

Each line is one event. A /submit writes a `classified` event; an /appeal (M5)
appends an `under_review` event for the same content_id. The current state of a
content_id is the *most recent* event for it ("latest event wins"); nothing is
ever overwritten.
"""
import json
import os
from dataclasses import asdict, dataclass
from typing import Optional

from config import LOG_FILE


@dataclass
class AuditEvent:
    """One row in logs/audit.jsonl.

    M4/M5 fields are Optional and stay None until those milestones fill them in;
    storing them as None now keeps every row the same shape from the start.
    """

    content_id: str
    creator_id: str
    timestamp: str  # ISO-8601 UTC
    event: str  # "classified" | "under_review"
    status: str  # "classified" | "under_review"
    llm_score: Optional[float] = None  # Signal 1 (live in M3)
    llm_rationale: Optional[str] = None
    stylometric_score: Optional[float] = None  # Signal 2 (M4)
    confidence: Optional[float] = None  # combined score (M4)
    attribution: Optional[str] = None  # band (M4)
    appeal_reasoning: Optional[str] = None  # present only on under_review events (M5)


def append_event(event: AuditEvent) -> None:
    """Append one event as a single JSON line."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(event)) + "\n")


def read_events(limit: Optional[int] = None) -> list[dict]:
    """Return audit events oldest-first; the last `limit` if given."""
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        events = [json.loads(line) for line in f if line.strip()]
    return events[-limit:] if limit else events
