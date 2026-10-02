"""
app/proactive/__init__.py — Proactive Intelligence Engine package.

Exports the main engine and alert models for external use.
"""
from app.proactive.engine import ProactiveIntelligenceEngine
from app.proactive.models import ProactiveAlert, AlertSeverity, AlertType

__all__ = [
    "ProactiveIntelligenceEngine",
    "ProactiveAlert",
    "AlertSeverity",
    "AlertType",
]
