"""
app/proactive/models.py — Data models for the Proactive Intelligence Engine.

ProactiveAlert is the core unit of proactive insight:
  - Stored in SQLite/PostgreSQL via the db_models.ProactiveAlertRecord ORM.
  - Delivered to the frontend via SSE push at /api/v1/proactive/stream.
  - Fetched by REST at /api/v1/proactive/alerts.

Design principles:
  - All alerts carry a confidence score (0–1). Low-confidence alerts are logged
    but NOT pushed to the user to prevent noise / alert fatigue.
  - Every alert has a severity (info / warning / critical) so the frontend can
    colour-code and filter appropriately.
  - Alert deduplication: an md5 of (user_id + alert_type + entity_key) is stored
    so the scanner never fires the same insight twice within DEDUP_WINDOW_HOURS.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AlertSeverity(str, Enum):
    INFO     = "info"
    WARNING  = "warning"
    CRITICAL = "critical"


class AlertType(str, Enum):
    # Document-level
    CROSS_DOCUMENT_MATCH    = "cross_document_match"     # Two docs share entity / address
    TEMPORAL_ANOMALY        = "temporal_anomaly"         # Incident before policy start, etc.
    ENTITY_COLLISION        = "entity_collision"         # Same entity appears in conflicting roles

    # System-level
    DRIFT_DETECTED          = "drift_detected"           # PSI / KS drift threshold exceeded
    HIGH_HALLUCINATION_RATE = "high_hallucination_rate"  # Recent FAIL evidence verdicts spike
    COST_SPIKE              = "cost_spike"               # Rolling USD cost > threshold

    # Daily briefing
    MORNING_BRIEFING        = "morning_briefing"         # Scheduled overnight activity summary


# Minimum confidence to PUSH an alert to the user (alerts below this are still stored)
PUSH_CONFIDENCE_THRESHOLD = 0.65

# Suppress duplicate alerts within this window (hours)
DEDUP_WINDOW_HOURS = 12


@dataclass
class ProactiveAlert:
    """
    A single proactive intelligence insight.

    Attributes
    ----------
    user_id       : Owner of this alert.
    alert_type    : Category of insight (AlertType enum).
    severity      : Visual severity level for the UI.
    title         : Short headline (≤ 80 chars), shown in the notification bell.
    message       : Full human-readable markdown explanation.
    confidence    : 0–1. Alerts below PUSH_CONFIDENCE_THRESHOLD are stored but not pushed.
    entity_key    : Canonical key used for deduplication (e.g. entity name, doc_id pair).
    source_doc_ids: List of document IDs that triggered this alert.
    metadata      : Free-form dict for extra structured data the frontend can use.
    alert_id      : Auto-generated stable dedup key (md5 of user_id+type+entity_key).
    created_at    : Unix timestamp of when this alert was generated.
    is_read       : Whether the user has acknowledged/dismissed it.
    """
    user_id:        str
    alert_type:     AlertType
    severity:       AlertSeverity
    title:          str
    message:        str
    confidence:     float               = 0.9
    entity_key:     str                 = ""
    source_doc_ids: list[str]           = field(default_factory=list)
    metadata:       dict                = field(default_factory=dict)
    alert_id:       str                 = field(init=False)
    created_at:     float               = field(default_factory=time.time)
    is_read:        bool                = False

    def __post_init__(self) -> None:
        raw = f"{self.user_id}:{self.alert_type}:{self.entity_key}"
        self.alert_id = hashlib.md5(raw.encode()).hexdigest()

    @property
    def should_push(self) -> bool:
        """True when confidence is high enough to show to the user in real-time."""
        return self.confidence >= PUSH_CONFIDENCE_THRESHOLD

    def to_dict(self) -> dict:
        return {
            "alert_id":      self.alert_id,
            "user_id":       self.user_id,
            "alert_type":    self.alert_type.value,
            "severity":      self.severity.value,
            "title":         self.title,
            "message":       self.message,
            "confidence":    round(self.confidence, 3),
            "entity_key":    self.entity_key,
            "source_doc_ids": self.source_doc_ids,
            "metadata":      self.metadata,
            "created_at":    self.created_at,
            "is_read":       self.is_read,
        }
