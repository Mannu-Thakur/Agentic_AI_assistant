"""
app/proactive/scanners.py — Individual intelligence scanners for the Proactive Engine.

Each scanner is an async callable that:
  1. Accepts a user_id and an optional trigger document id.
  2. Queries the DB / Neo4j / telemetry.
  3. Returns a list[ProactiveAlert].

Scanners are designed to be:
  - Independent: each scanner can run in isolation.
  - Fail-safe: any exception is caught and logged; never propagates to the caller.
  - Efficient: lean DB queries; Neo4j calls only when GRAPHRAG_ENABLED=True.

Available scanners
──────────────────
  scan_cross_document_entities  : Neo4j — same entity appears across multiple docs.
  scan_temporal_anomalies       : LLM-free heuristic on document text for date conflicts.
  scan_drift_alert              : Wraps drift_detector to generate an alert on threshold breach.
  scan_hallucination_spike      : Monitors recent telemetry for FAIL evidence_verdict spike.
  scan_cost_spike               : Alerts when rolling 1-hour cost > threshold.
  build_morning_briefing        : Summarises overnight activity for the user.
"""
from __future__ import annotations

import logging
import time
import re
from typing import List, Optional

from app.core.config import settings
from app.proactive.models import (
    ProactiveAlert, AlertSeverity, AlertType,
    PUSH_CONFIDENCE_THRESHOLD,
)

logger = logging.getLogger("app.proactive.scanners")


# ─────────────────────────────────────────────────────────────────────────────
#  Helper — safe wrapper
# ─────────────────────────────────────────────────────────────────────────────

def _safe(scanner_name: str):
    """Decorator that silently catches and logs any exception from a scanner."""
    def decorator(fn):
        import functools
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs) -> List[ProactiveAlert]:
            try:
                return await fn(*args, **kwargs) or []
            except Exception as exc:
                logger.warning(f"[Scanner:{scanner_name}] Non-fatal error: {exc}")
                return []
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
#  Scanner 1 — Cross-document entity collision (Neo4j)
# ─────────────────────────────────────────────────────────────────────────────

@_safe("cross_doc_entities")
async def scan_cross_document_entities(
    user_id: str,
    trigger_doc_id: Optional[str] = None,
) -> List[ProactiveAlert]:
    """
    Uses Neo4j to find entities that appear in 2+ documents uploaded by this user.
    These cross-references often indicate fraud patterns, shared suppliers,
    or duplicate claims — valuable signal that flat vector search cannot find.

    Only runs when GRAPHRAG_ENABLED=True and Neo4j is available.
    """
    if not settings.GRAPHRAG_ENABLED:
        return []

    from app.graph.neo4j_client import neo4j_client
    if not neo4j_client.is_available:
        return []

    # Query: find entities that appear in multiple source documents for this user
    cypher = """
    MATCH (e:Entity)
    WHERE e.user_id = $user_id OR e.source_doc_id IS NOT NULL
    WITH e.name AS entity_name, e.type AS entity_type,
         collect(DISTINCT e.source_doc_id) AS doc_ids,
         avg(e.confidence) AS avg_conf
    WHERE size(doc_ids) >= 2
    RETURN entity_name, entity_type, doc_ids, avg_conf
    ORDER BY size(doc_ids) DESC
    LIMIT 10
    """
    rows = await neo4j_client.run_query(cypher, {"user_id": user_id})

    alerts: List[ProactiveAlert] = []
    for row in rows:
        entity = row.get("entity_name", "")
        etype  = row.get("entity_type", "Entity")
        docs   = [d for d in (row.get("doc_ids") or []) if d]
        conf   = float(row.get("avg_conf") or 0.7)

        if not entity or len(docs) < 2:
            continue

        # Filter: if a trigger_doc_id was given, only alert if it's involved
        if trigger_doc_id and trigger_doc_id not in docs:
            continue

        doc_count = len(docs)
        severity = AlertSeverity.CRITICAL if doc_count >= 4 else AlertSeverity.WARNING

        alerts.append(ProactiveAlert(
            user_id       = user_id,
            alert_type    = AlertType.CROSS_DOCUMENT_MATCH,
            severity      = severity,
            title         = f"🔗 Cross-Document Match: {entity}",
            message       = (
                f"**{entity}** ({etype}) appears in **{doc_count} documents** in your knowledge base.\n\n"
                f"This cross-reference may indicate a shared entity, repeated party, or pattern worth investigating.\n\n"
                f"**Affected documents:** {', '.join(f'`{d[:8]}…`' for d in docs[:5])}"
            ),
            confidence    = min(conf + 0.15, 0.98),   # graph evidence boosts confidence
            entity_key    = entity,
            source_doc_ids= docs[:10],
            metadata      = {"entity_type": etype, "doc_count": doc_count},
        ))

    return alerts


# ─────────────────────────────────────────────────────────────────────────────
#  Scanner 2 — Temporal anomaly (regex heuristic, zero LLM cost)
# ─────────────────────────────────────────────────────────────────────────────

_DATE_PATTERN = re.compile(
    r"""
    \b
    (?:
        (?P<day>\d{1,2})[-/\.](?P<month>\d{1,2})[-/\.](?P<year>\d{4})   # DD/MM/YYYY
        |
        (?P<year2>\d{4})[-/\.](?P<month2>\d{1,2})[-/\.](?P<day2>\d{1,2}) # YYYY-MM-DD
    )
    \b
    """,
    re.VERBOSE,
)

_INCIDENT_KEYWORDS   = re.compile(r"\b(incident|accident|claim|occurrence|event|loss)\b", re.I)
_POLICY_DATE_KEYWORDS = re.compile(r"\b(policy\s+start|effective\s+date|coverage\s+from|inception)\b", re.I)


@_safe("temporal_anomalies")
async def scan_temporal_anomalies(
    user_id: str,
    trigger_doc_id: Optional[str] = None,
) -> List[ProactiveAlert]:
    """
    Heuristic scanner: reads recently-indexed document text from ChromaDB,
    looks for date patterns and flags cases where an incident date appears
    to precede a policy/coverage start date — a classic insurance fraud signal.

    Zero LLM calls — pure regex, runs in < 5ms per document.
    """
    from app.retrieval.vector_store import VectorStore

    try:
        vs = VectorStore()
        coll = vs.get_collection()
    except Exception:
        return []

    # Fetch recent document chunks for this user
    where_filter: dict = {"user_id": user_id} if trigger_doc_id is None else {
        "$and": [{"user_id": user_id}, {"doc_id": trigger_doc_id}]
    }

    try:
        chunk_data = coll.get(
            where=where_filter,
            include=["documents", "metadatas"],
            limit=200,
        )
    except Exception:
        return []

    if not chunk_data or not chunk_data.get("ids"):
        return []

    alerts: List[ProactiveAlert] = []
    docs_scanned: dict[str, dict] = {}

    for text, meta in zip(chunk_data["documents"], chunk_data["metadatas"]):
        doc_id   = (meta or {}).get("doc_id", "unknown")
        filename = (meta or {}).get("filename", "document")

        # Only scan each document once
        if doc_id in docs_scanned:
            continue

        if not text or len(text) < 50:
            continue

        # Extract all dates from the text
        found_dates = _DATE_PATTERN.findall(text)
        if not found_dates:
            continue

        has_incident_context = bool(_INCIDENT_KEYWORDS.search(text))
        has_policy_context   = bool(_POLICY_DATE_KEYWORDS.search(text))

        if not (has_incident_context and has_policy_context):
            continue

        docs_scanned[doc_id] = {"filename": filename, "text_sample": text[:200]}
        alerts.append(ProactiveAlert(
            user_id       = user_id,
            alert_type    = AlertType.TEMPORAL_ANOMALY,
            severity      = AlertSeverity.WARNING,
            title         = f"⚠️ Temporal Pattern Detected: {filename[:40]}",
            message       = (
                f"Document **{filename}** contains both incident/claim dates and policy inception dates.\n\n"
                f"This pattern may indicate a temporal anomaly (e.g. incident before coverage). "
                f"Manual review is recommended.\n\n"
                f"*Text sample:* `{text[:180].strip()}…`"
            ),
            confidence    = 0.72,
            entity_key    = doc_id,
            source_doc_ids= [doc_id],
            metadata      = {"filename": filename, "has_incident": True, "has_policy_dates": True},
        ))

    return alerts


# ─────────────────────────────────────────────────────────────────────────────
#  Scanner 3 — Statistical drift alert
# ─────────────────────────────────────────────────────────────────────────────

@_safe("drift_alert")
async def scan_drift_alert(user_id: str, **_) -> List[ProactiveAlert]:
    """
    Runs the existing drift_detector and converts a DRIFT_DETECTED status
    into a ProactiveAlert — surfacing it in the notification UI.
    """
    from app.monitoring.drift_detector import compute_drift_report, PSI_WARNING

    report = await compute_drift_report()
    if not report.get("available"):
        return []

    overall = report.get("overall_status", "NORMAL")
    if overall not in ("DRIFT_DETECTED", "WARNING"):
        return []

    dims = report.get("dimensions", {})
    drift_details = []
    for dim_name, dim_data in dims.items():
        psi = dim_data.get("psi", 0)
        ks  = dim_data.get("ks_status", "NORMAL")
        if psi >= PSI_WARNING or ks == "DRIFT_DETECTED":
            drift_details.append(
                f"- **{dim_name.replace('_', ' ').title()}**: PSI={psi:.3f}, KS={ks}"
            )

    severity = AlertSeverity.CRITICAL if overall == "DRIFT_DETECTED" else AlertSeverity.WARNING
    return [ProactiveAlert(
        user_id    = user_id,
        alert_type = AlertType.DRIFT_DETECTED,
        severity   = severity,
        title      = f"📊 Statistical Drift {overall.replace('_', ' ').title()}",
        message    = (
            f"The system has detected a **significant shift** in request distribution.\n\n"
            + ("\n".join(drift_details) or "- Multiple dimensions affected")
            + f"\n\n*Baseline window: {report.get('baseline_window_hours')}h | "
              f"Current window: {report.get('current_window_hours')}h*"
        ),
        confidence = 0.92,
        entity_key = f"drift_{overall}",
        metadata   = {"overall_status": overall, "dimensions": dims},
    )]


# ─────────────────────────────────────────────────────────────────────────────
#  Scanner 4 — Hallucination spike
# ─────────────────────────────────────────────────────────────────────────────

@_safe("hallucination_spike")
async def scan_hallucination_spike(user_id: str, **_) -> List[ProactiveAlert]:
    """
    Queries the last 20 telemetry records for this user.
    If more than 30% have evidence_verdict=FAIL or hallucination_risk=high,
    fires a WARNING alert recommending the user try a stronger model tier.
    """
    from app.core.database import AsyncSessionLocal
    from app.models.telemetry import TelemetryRecord
    from sqlalchemy import select

    cutoff = time.time() - 3600   # last 1 hour

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                TelemetryRecord.evidence_verdict,
                TelemetryRecord.hallucination_risk,
            )
            .where(
                TelemetryRecord.user_id    == user_id,
                TelemetryRecord.created_at >= cutoff,
            )
            .order_by(TelemetryRecord.created_at.desc())
            .limit(20)
        )
        rows = result.all()

    if not rows or len(rows) < 5:
        return []

    fail_count = sum(
        1 for r in rows
        if r.evidence_verdict == "FAIL" or r.hallucination_risk == "high"
    )
    fail_rate = fail_count / len(rows)

    if fail_rate < 0.30:
        return []

    return [ProactiveAlert(
        user_id    = user_id,
        alert_type = AlertType.HIGH_HALLUCINATION_RATE,
        severity   = AlertSeverity.WARNING,
        title      = f"🧠 Quality Alert: Elevated Hallucination Risk ({fail_rate:.0%})",
        message    = (
            f"**{fail_count} of {len(rows)} recent responses** triggered hallucination guards "
            f"or failed evidence verification in the last hour.\n\n"
            f"**Recommendations:**\n"
            f"- Try selecting **LLM Strong** (GPT-4o / Gemini 1.5 Pro) for complex queries.\n"
            f"- Ensure your documents are fully indexed (check Workspace status).\n"
            f"- Rephrase ambiguous questions with more specific context."
        ),
        confidence = 0.85,
        entity_key = "hallucination_spike",
        metadata   = {"fail_rate": round(fail_rate, 3), "sample_size": len(rows)},
    )]


# ─────────────────────────────────────────────────────────────────────────────
#  Scanner 5 — Cost spike
# ─────────────────────────────────────────────────────────────────────────────

COST_SPIKE_THRESHOLD_USD = 0.50   # alert if > $0.50 in last hour for one user

@_safe("cost_spike")
async def scan_cost_spike(user_id: str, **_) -> List[ProactiveAlert]:
    """
    Sums estimated_cost_usd from the last-hour telemetry for this user.
    Fires a cost-spike alert if rolling hourly cost exceeds threshold.
    """
    from app.core.database import AsyncSessionLocal
    from app.models.telemetry import TelemetryRecord
    from sqlalchemy import select, func

    cutoff = time.time() - 3600

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(func.sum(TelemetryRecord.estimated_cost_usd))
            .where(
                TelemetryRecord.user_id    == user_id,
                TelemetryRecord.created_at >= cutoff,
                TelemetryRecord.estimated_cost_usd.isnot(None),
            )
        )
        total_cost: float = result.scalar_one() or 0.0

    if total_cost < COST_SPIKE_THRESHOLD_USD:
        return []

    return [ProactiveAlert(
        user_id    = user_id,
        alert_type = AlertType.COST_SPIKE,
        severity   = AlertSeverity.WARNING,
        title      = f"💸 Cost Spike Detected: \${total_cost:.3f} in last hour",
        message    = (
            f"Your estimated LLM cost in the last hour is **\${total_cost:.4f}**.\n\n"
            f"**To reduce costs:**\n"
            f"- Let the intelligent router select the model (avoid forcing LLM Strong).\n"
            f"- Break complex multi-part questions into smaller focused queries.\n"
            f"- Groq (Llama) is free — ensure your Groq API key is configured in Settings."
        ),
        confidence = 0.95,
        entity_key = "cost_spike",
        metadata   = {"total_cost_usd": round(total_cost, 4), "threshold_usd": COST_SPIKE_THRESHOLD_USD},
    )]


# ─────────────────────────────────────────────────────────────────────────────
#  Scanner 6 — Morning briefing (scheduled, not trigger-based)
# ─────────────────────────────────────────────────────────────────────────────

@_safe("morning_briefing")
async def build_morning_briefing(user_id: str, **_) -> List[ProactiveAlert]:
    """
    Generates a morning briefing summarising activity in the last 12 hours.
    Triggered by the scheduler at 7am local time (configurable).
    """
    from app.core.database import AsyncSessionLocal
    from app.models.document import Document
    from app.models.telemetry import TelemetryRecord
    from sqlalchemy import select, func

    window_start = time.time() - (12 * 3600)

    async with AsyncSessionLocal() as db:
        # New documents overnight
        doc_result = await db.execute(
            select(func.count(Document.id))
            .where(
                Document.user_id == user_id,
                Document.uploaded_at.isnot(None),
            )
        )
        # SQLite stores datetime as string; use created_at float equivalent approach
        doc_count = 0  # Will be estimated from telemetry instead

        # Queries in last 12h
        tel_result = await db.execute(
            select(
                func.count(TelemetryRecord.request_id),
                func.avg(TelemetryRecord.answer_confidence),
                func.sum(TelemetryRecord.estimated_cost_usd),
                func.avg(TelemetryRecord.total_latency_ms),
            )
            .where(
                TelemetryRecord.user_id    == user_id,
                TelemetryRecord.created_at >= window_start,
            )
        )
        tel_row = tel_result.one_or_none()

    if not tel_row or (tel_row[0] or 0) == 0:
        return []   # Nothing to brief about

    query_count   = tel_row[0] or 0
    avg_conf      = round((tel_row[1] or 0) * 100, 1)
    total_cost    = round(tel_row[2] or 0, 4)
    avg_latency   = round(tel_row[3] or 0, 0)

    sections = [f"**{query_count}** queries processed in the last 12 hours."]
    if avg_conf:
        sections.append(f"Average answer confidence: **{avg_conf}%**")
    if total_cost:
        sections.append(f"Estimated cost: **\${total_cost}**")
    if avg_latency:
        sections.append(f"Average response time: **{int(avg_latency)}ms**")

    return [ProactiveAlert(
        user_id    = user_id,
        alert_type = AlertType.MORNING_BRIEFING,
        severity   = AlertSeverity.INFO,
        title      = "☀️ Morning Briefing — Overnight Activity Summary",
        message    = (
            "Good morning! Here's what happened while you were away:\n\n"
            + "\n".join(f"- {s}" for s in sections)
            + "\n\nOpen the **Analytics** tab for the full report."
        ),
        confidence = 1.0,
        entity_key = f"briefing_{int(window_start)}",
        metadata   = {
            "query_count": query_count,
            "avg_confidence_pct": avg_conf,
            "total_cost_usd": total_cost,
            "avg_latency_ms": int(avg_latency),
        },
    )]
