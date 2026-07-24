"""
app/core/telemetry.py — Production observability telemetry (Phase 3).

Tracks per-request metrics and emits structured JSON logs for ingestion
by log aggregators (Loki, CloudWatch, Datadog, etc.).

Tracked dimensions:
  - Routing decisions (intent, is_ambiguous, needs_retrieval)
  - Retrieval latency + confidence
  - Tool latency per tool
  - LLM latency per provider
  - Retry counts (retrieval + tool)
  - Hallucination rate (evidence checker verdicts)
  - Citation coverage (% of chunks cited in response)
  - Cache hit ratios (retrieval, embedding, web search)
  - Token usage estimates
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.core.telemetry")


@dataclass
class RequestTelemetry:
    """
    Collects all telemetry for a single agent invocation.
    Instantiate at request start, call record_*() methods during processing,
    and finalize() at the end to emit a structured log.
    """
    request_id: str
    user_id: str
    chat_id: str

    # Routing
    intent: str              = "UNKNOWN"
    is_ambiguous: bool       = False
    needs_retrieval: bool    = False

    # Retrieval
    retrieval_latency_ms: float  = 0.0
    retrieval_confidence: float  = 0.0
    retrieval_retries: int       = 0
    chunks_retrieved: int        = 0
    chunks_after_rerank: int     = 0
    chunks_after_compress: int   = 0

    # Tools
    tool_results: List[Dict[str, Any]] = field(default_factory=list)

    # LLM
    llm_latency_ms: float    = 0.0
    llm_provider: str        = "unknown"
    llm_model: str           = "unknown"
    token_estimate: int      = 0

    # Evidence / hallucination
    answer_confidence: float        = 1.0
    hallucination_risk: str         = "low"
    unsupported_claims_count: int   = 0
    evidence_verdict: str           = "PASS"

    # Citation
    citations_count: int            = 0

    # Cache
    cache_stats: List[Dict[str, Any]] = field(default_factory=list)

    # Reflection
    reflection_passed: bool  = True
    reflection_iterations: int = 0

    # Total
    total_latency_ms: float  = 0.0
    _start_time: float       = field(default_factory=time.monotonic, repr=False)

    # ── Recording methods ──────────────────────────────────────────────────────

    def record_routing(self, intent: str, is_ambiguous: bool, needs_retrieval: bool) -> None:
        self.intent         = intent
        self.is_ambiguous   = is_ambiguous
        self.needs_retrieval = needs_retrieval

    def record_retrieval(
        self,
        latency_ms: float,
        confidence: float,
        retries: int,
        chunks_retrieved: int,
        chunks_reranked: int = 0,
        chunks_compressed: int = 0,
    ) -> None:
        self.retrieval_latency_ms   = latency_ms
        self.retrieval_confidence   = confidence
        self.retrieval_retries      = retries
        self.chunks_retrieved       = chunks_retrieved
        self.chunks_after_rerank    = chunks_reranked
        self.chunks_after_compress  = chunks_compressed

    def record_tool(self, tool_id: str, tool_name: str, status: str, latency_ms: float) -> None:
        self.tool_results.append({
            "id":         tool_id,
            "tool":       tool_name,
            "status":     status,
            "latency_ms": latency_ms,
        })

    def record_llm(self, provider: str, model: str, latency_ms: float, response_text: str = "") -> None:
        self.llm_latency_ms = latency_ms
        self.llm_provider   = provider
        self.llm_model      = model
        # Rough token estimate: 4 chars ≈ 1 token
        self.token_estimate = len(response_text) // 4

    def record_evidence(
        self,
        verdict: str,
        confidence: float,
        hallucination_risk: str,
        unsupported_count: int,
        citations_count: int,
    ) -> None:
        self.evidence_verdict        = verdict
        self.answer_confidence       = confidence
        self.hallucination_risk      = hallucination_risk
        self.unsupported_claims_count = unsupported_count
        self.citations_count         = citations_count

    def record_reflection(self, passed: bool, iterations: int) -> None:
        self.reflection_passed     = passed
        self.reflection_iterations = iterations

    def attach_cache_stats(self, stats: List[Dict[str, Any]]) -> None:
        self.cache_stats = stats

    def finalize(self) -> Dict[str, Any]:
        """
        Compute total latency, emit a structured JSON log line, and return
        the telemetry dict for inclusion in the API response (if desired).
        """
        self.total_latency_ms = round((time.monotonic() - self._start_time) * 1000, 1)

        payload = {
            "event":                   "agent_request",
            "request_id":              self.request_id,
            "user_id":                 self.user_id,
            "chat_id":                 self.chat_id,
            "intent":                  self.intent,
            "is_ambiguous":            self.is_ambiguous,
            "needs_retrieval":         self.needs_retrieval,
            "retrieval_latency_ms":    self.retrieval_latency_ms,
            "retrieval_confidence":    self.retrieval_confidence,
            "retrieval_retries":       self.retrieval_retries,
            "chunks_retrieved":        self.chunks_retrieved,
            "chunks_after_rerank":     self.chunks_after_rerank,
            "chunks_after_compress":   self.chunks_after_compress,
            "tools_executed":          len(self.tool_results),
            "tool_results":            self.tool_results,
            "llm_provider":            self.llm_provider,
            "llm_model":               self.llm_model,
            "llm_latency_ms":          self.llm_latency_ms,
            "token_estimate":          self.token_estimate,
            "evidence_verdict":        self.evidence_verdict,
            "answer_confidence":       self.answer_confidence,
            "hallucination_risk":      self.hallucination_risk,
            "unsupported_claims":      self.unsupported_claims_count,
            "citations_count":         self.citations_count,
            "reflection_passed":       self.reflection_passed,
            "reflection_iterations":   self.reflection_iterations,
            "cache_stats":             self.cache_stats,
            "total_latency_ms":        self.total_latency_ms,
        }

        logger.info(json.dumps(payload))
        return payload
