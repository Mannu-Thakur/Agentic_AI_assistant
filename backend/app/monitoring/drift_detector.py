"""
app/monitoring/drift_detector.py — Data drift detection for GenAI observability.

Implements genuine statistical drift detection on real application data:
  - Query complexity score distribution drift (PSI)
  - Response confidence drift (KS test)
  - Retrieval quality drift (PSI on chunk counts)
  - Latency drift (KS test)

Drift is measured against a baseline window vs the current window.
All thresholds are configurable.

IMPORTANT: This monitors real application metrics (from telemetry DB),
NOT fake synthetic distributions. Results reflect actual system behavior.

Reference metrics:
  PSI < 0.1  = NORMAL (no significant drift)
  PSI 0.1-0.2 = WARNING (moderate drift)
  PSI > 0.2   = DRIFT DETECTED
  KS p-value < 0.05 = statistically significant drift
"""
from __future__ import annotations

import logging
import math
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("app.monitoring.drift_detector")

# PSI thresholds
PSI_NORMAL = 0.1
PSI_WARNING = 0.2

# KS test p-value threshold for significance
KS_SIGNIFICANCE = 0.05


def _compute_psi(
    baseline: List[float],
    current: List[float],
    n_bins: int = 10,
    epsilon: float = 1e-4,
) -> float:
    """
    Compute Population Stability Index (PSI) between baseline and current distributions.

    PSI = sum((current_pct - baseline_pct) * ln(current_pct / baseline_pct))

    Args:
        baseline: Reference distribution values
        current: Current distribution values
        n_bins: Number of histogram bins
        epsilon: Small constant to avoid log(0)

    Returns:
        PSI value (0 = identical, > 0.2 = significant drift)
    """
    if not baseline or not current:
        return 0.0

    all_values = baseline + current
    min_val = min(all_values)
    max_val = max(all_values)

    if max_val == min_val:
        return 0.0

    bin_width = (max_val - min_val) / n_bins
    bins = [min_val + i * bin_width for i in range(n_bins + 1)]

    def _bin_counts(values: List[float]) -> List[float]:
        counts = [0] * n_bins
        for v in values:
            idx = min(int((v - min_val) / bin_width), n_bins - 1)
            counts[idx] += 1
        total = sum(counts) or 1
        return [(c / total) + epsilon for c in counts]

    baseline_pct = _bin_counts(baseline)
    current_pct = _bin_counts(current)

    psi = sum(
        (c - b) * math.log(c / b)
        for b, c in zip(baseline_pct, current_pct)
    )
    return round(psi, 4)


def _compute_ks_statistic(
    baseline: List[float],
    current: List[float],
) -> Tuple[float, str]:
    """
    Simplified KS statistic (max CDF difference).
    Returns (ks_statistic, drift_status).

    Note: This is the KS D-statistic only. For a proper p-value,
    install scipy: from scipy.stats import ks_2samp.
    We use a simple threshold on D as a practical proxy.
    """
    if not baseline or not current:
        return 0.0, "NORMAL"

    try:
        from scipy.stats import ks_2samp
        stat, p_value = ks_2samp(baseline, current)
        if p_value < KS_SIGNIFICANCE and stat > 0.2:
            status = "DRIFT_DETECTED"
        elif p_value < KS_SIGNIFICANCE:
            status = "WARNING"
        else:
            status = "NORMAL"
        return round(stat, 4), status
    except ImportError:
        # Fallback: manual D-statistic
        combined = sorted(set(baseline + current))
        n1, n2 = len(baseline), len(current)
        base_set = sorted(baseline)
        curr_set = sorted(current)

        max_diff = 0.0
        for v in combined:
            b_cdf = sum(1 for x in base_set if x <= v) / n1
            c_cdf = sum(1 for x in curr_set if x <= v) / n2
            max_diff = max(max_diff, abs(b_cdf - c_cdf))

        status = "DRIFT_DETECTED" if max_diff > 0.3 else ("WARNING" if max_diff > 0.15 else "NORMAL")
        return round(max_diff, 4), status


def _psi_status(psi: float) -> str:
    """Classify PSI value into drift status."""
    if psi < PSI_NORMAL:
        return "NORMAL"
    elif psi < PSI_WARNING:
        return "WARNING"
    else:
        return "DRIFT_DETECTED"


async def compute_drift_report(
    baseline_window_hours: int = 24,
    current_window_hours: int = 1,
) -> Dict[str, Any]:
    """
    Compute drift metrics comparing baseline vs current telemetry windows.

    Args:
        baseline_window_hours: Hours of historical data for baseline
        current_window_hours: Hours of recent data for current window

    Returns:
        Dict with drift metrics for each dimension
    """
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.telemetry import TelemetryRecord
        from sqlalchemy import select
        now = time.time()
        baseline_start = now - (baseline_window_hours * 3600.0)
        current_start = now - (current_window_hours * 3600.0)

        async with AsyncSessionLocal() as db:
            # Fetch baseline window
            baseline_result = await db.execute(
                select(
                    TelemetryRecord.complexity_score,
                    TelemetryRecord.answer_confidence,
                    TelemetryRecord.chunks_retrieved,
                    TelemetryRecord.total_latency_ms,
                )
                .where(TelemetryRecord.created_at >= baseline_start)
                .where(TelemetryRecord.created_at < current_start)
            )
            baseline_rows = baseline_result.all()

            # Fetch current window
            current_result = await db.execute(
                select(
                    TelemetryRecord.complexity_score,
                    TelemetryRecord.answer_confidence,
                    TelemetryRecord.chunks_retrieved,
                    TelemetryRecord.total_latency_ms,
                )
                .where(TelemetryRecord.created_at >= current_start)
            )
            current_rows = current_result.all()

    except Exception as e:
        logger.warning(f"[DriftDetector] DB query failed: {e}")
        return {"available": False, "error": str(e)}

    if len(baseline_rows) < 10:
        return {
            "available": True,
            "message": f"Insufficient baseline data ({len(baseline_rows)} records). Need at least 10 records in the {baseline_window_hours}h baseline window.",
            "baseline_count": len(baseline_rows),
            "current_count": len(current_rows),
        }

    def _extract(rows, col_idx):
        return [float(r[col_idx]) for r in rows if r[col_idx] is not None]

    # Complexity drift
    base_complexity = _extract(baseline_rows, 0)
    curr_complexity = _extract(current_rows, 0)
    complexity_psi = _compute_psi(base_complexity, curr_complexity) if curr_complexity else 0.0

    # Confidence drift
    base_confidence = _extract(baseline_rows, 1)
    curr_confidence = _extract(current_rows, 1)
    confidence_psi = _compute_psi(base_confidence, curr_confidence) if curr_confidence else 0.0
    confidence_ks, confidence_ks_status = _compute_ks_statistic(base_confidence, curr_confidence) if curr_confidence else (0.0, "NORMAL")

    # Retrieval quality drift
    base_chunks = _extract(baseline_rows, 2)
    curr_chunks = _extract(current_rows, 2)
    chunks_psi = _compute_psi(base_chunks, curr_chunks) if curr_chunks else 0.0

    # Latency drift
    base_latency = _extract(baseline_rows, 3)
    curr_latency = _extract(current_rows, 3)
    latency_ks, latency_ks_status = _compute_ks_statistic(base_latency, curr_latency) if curr_latency else (0.0, "NORMAL")

    # Overall drift status
    all_statuses = [
        _psi_status(complexity_psi),
        _psi_status(confidence_psi),
        _psi_status(chunks_psi),
        latency_ks_status,
        confidence_ks_status,
    ]
    if "DRIFT_DETECTED" in all_statuses:
        overall_status = "DRIFT_DETECTED"
    elif "WARNING" in all_statuses:
        overall_status = "WARNING"
    else:
        overall_status = "NORMAL"

    return {
        "available": True,
        "timestamp": now,
        "baseline_window_hours": baseline_window_hours,
        "current_window_hours": current_window_hours,
        "baseline_count": len(baseline_rows),
        "current_count": len(current_rows),
        "overall_status": overall_status,
        "dimensions": {
            "query_complexity": {
                "psi": complexity_psi,
                "status": _psi_status(complexity_psi),
                "baseline_mean": round(sum(base_complexity) / max(len(base_complexity), 1), 3),
                "current_mean": round(sum(curr_complexity) / max(len(curr_complexity), 1), 3) if curr_complexity else None,
            },
            "answer_confidence": {
                "psi": confidence_psi,
                "psi_status": _psi_status(confidence_psi),
                "ks_statistic": confidence_ks,
                "ks_status": confidence_ks_status,
                "baseline_mean": round(sum(base_confidence) / max(len(base_confidence), 1), 3),
                "current_mean": round(sum(curr_confidence) / max(len(curr_confidence), 1), 3) if curr_confidence else None,
            },
            "retrieval_quality": {
                "psi": chunks_psi,
                "status": _psi_status(chunks_psi),
                "baseline_mean_chunks": round(sum(base_chunks) / max(len(base_chunks), 1), 1),
                "current_mean_chunks": round(sum(curr_chunks) / max(len(curr_chunks), 1), 1) if curr_chunks else None,
            },
            "response_latency": {
                "ks_statistic": latency_ks,
                "status": latency_ks_status,
                "baseline_mean_ms": round(sum(base_latency) / max(len(base_latency), 1), 1),
                "current_mean_ms": round(sum(curr_latency) / max(len(curr_latency), 1), 1) if curr_latency else None,
            },
        },
        "thresholds": {
            "psi_normal": PSI_NORMAL,
            "psi_warning": PSI_WARNING,
            "ks_significance": KS_SIGNIFICANCE,
        },
    }
