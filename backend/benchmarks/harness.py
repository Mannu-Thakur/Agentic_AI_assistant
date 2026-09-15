"""
benchmarks/harness.py — Core evaluation harness for the Omni AI benchmark framework.

Provides:
  - OmniClient:      Authenticates + streams chat responses from the FastAPI backend
  - EvalResult:      Single-case evaluation result
  - SuiteResult:     Aggregated results for a full capability benchmark run
  - BenchmarkRunner: Orchestrates concurrent test case execution
  - load_dataset:    Reads JSONL benchmark datasets
  - save_results:    Persists results to disk
"""

from __future__ import annotations

import asyncio
import json
import logging
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, List, Optional

import httpx

from benchmarks.config import BenchmarkConfig, load_config

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
#  Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EvalResult:
    """Result for a single benchmark test case."""
    case_id:         str
    capability:      str
    score:           float              # 0.0 – 1.0 normalised
    raw_metrics:     dict[str, Any]
    latency_ms:      int
    tokens_used:     int = 0
    trace:           dict[str, Any] = field(default_factory=dict)
    intent_detected: str = ""
    generation_mode: str = ""
    error:           Optional[str] = None
    timestamp:       str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def passed(self, threshold: float = 0.60) -> bool:
        return self.score >= threshold and self.error is None

    def to_dict(self) -> dict:
        return {
            "case_id":         self.case_id,
            "capability":      self.capability,
            "score":           round(self.score, 4),
            "raw_metrics":     self.raw_metrics,
            "latency_ms":      self.latency_ms,
            "tokens_used":     self.tokens_used,
            "intent_detected": self.intent_detected,
            "generation_mode": self.generation_mode,
            "error":           self.error,
            "timestamp":       self.timestamp,
        }


@dataclass
class SuiteResult:
    """Aggregated results for a full capability benchmark suite."""
    capability:      str
    cases:           List[EvalResult]
    mean_score:      float = 0.0
    std_score:       float = 0.0
    min_score:       float = 0.0
    max_score:       float = 0.0
    p50_latency_ms:  int   = 0
    p95_latency_ms:  int   = 0
    p99_latency_ms:  int   = 0
    pass_rate:       float = 0.0
    total_cases:     int   = 0
    error_count:     int   = 0
    run_timestamp:   str   = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_results(
        cls,
        capability: str,
        results: List[EvalResult],
        pass_threshold: float = 0.60,
    ) -> "SuiteResult":
        suite = cls(capability=capability, cases=results)
        suite.total_cases  = len(results)
        suite.error_count  = sum(1 for r in results if r.error is not None)

        scores    = [r.score for r in results]
        latencies = sorted(r.latency_ms for r in results)

        if scores:
            suite.mean_score = statistics.mean(scores)
            suite.std_score  = statistics.stdev(scores) if len(scores) > 1 else 0.0
            suite.min_score  = min(scores)
            suite.max_score  = max(scores)
            suite.pass_rate  = sum(1 for s in scores if s >= pass_threshold) / len(scores)

        if latencies:
            n = len(latencies)
            suite.p50_latency_ms = latencies[int(n * 0.50)]
            suite.p95_latency_ms = latencies[min(int(n * 0.95), n - 1)]
            suite.p99_latency_ms = latencies[min(int(n * 0.99), n - 1)]

        return suite

    def summary_dict(self) -> dict:
        return {
            "capability":     self.capability,
            "total_cases":    self.total_cases,
            "error_count":    self.error_count,
            "mean_score":     round(self.mean_score, 4),
            "std_score":      round(self.std_score, 4),
            "min_score":      round(self.min_score, 4),
            "max_score":      round(self.max_score, 4),
            "pass_rate":      round(self.pass_rate, 4),
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "run_timestamp":  self.run_timestamp,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  OmniClient — authenticates and streams chat from the FastAPI backend
# ─────────────────────────────────────────────────────────────────────────────

class OmniClient:
    """HTTP client for the Omni AI FastAPI backend."""

    def __init__(self, config: BenchmarkConfig) -> None:
        self.config  = config
        self._token: Optional[str] = None
        self._http   = httpx.AsyncClient(timeout=config.default_timeout_s)

    async def __aenter__(self) -> "OmniClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._http.aclose()

    async def authenticate(self) -> str:
        """POST to auth endpoint, cache and return JWT access token."""
        if self._token:
            return self._token

        resp = await self._http.post(
            self.config.auth_url,
            data={
                "username": self.config.bench_email,
                "password": self.config.bench_password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data.get("access_token") or data.get("token")
        if not self._token:
            raise ValueError(f"No token in auth response: {data}")
        logger.info("Authenticated as %s", self.config.bench_email)
        return self._token

    async def check_health(self) -> dict:
        """GET /api/v1/health — return health dict or raise."""
        resp = await self._http.get(self.config.health_url)
        resp.raise_for_status()
        return resp.json()

    async def stream_chat(
        self,
        message: str,
        token: str,
        model: str = "gemini-2.0-flash",
        conversation_id: Optional[str] = None,
        extra_headers: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        POST to /api/v1/chat/stream, consume all SSE events.

        Returns accumulated dict with:
          response_text, intent, generation_mode, answer_confidence,
          has_hallucination_risk, needs_retrieval, retrieval_confidence,
          document_relevance, tool_execution_results, execution_trace,
          web_status, sub_questions, latency_ms, telemetry
        """
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept":        "text/event-stream",
            "Content-Type":  "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)

        payload: dict[str, Any] = {
            "message": message,
            "model":   model,
            "stream":  True,
        }
        if conversation_id:
            payload["conversation_id"] = conversation_id

        # Accumulator
        acc: dict[str, Any] = {
            "response_text":          "",
            "intent":                 "",
            "generation_mode":        "",
            "answer_confidence":      0.0,
            "has_hallucination_risk": False,
            "needs_retrieval":        False,
            "retrieval_confidence":   0.0,
            "document_relevance":     "",
            "tool_execution_results": [],
            "execution_trace":        [],
            "web_status":             {},
            "sub_questions":          [],
            "latency_ms":             0,
            "telemetry":              {},
        }

        t0 = time.monotonic()

        async with self._http.stream(
            "POST",
            self.config.chat_url,
            json=payload,
            headers=headers,
            timeout=self.config.default_timeout_s,
        ) as resp:
            resp.raise_for_status()

            async for raw_line in resp.aiter_lines():
                line = raw_line.strip()
                if not line or not line.startswith("data:"):
                    continue

                data_str = line[len("data:"):].strip()
                if not data_str:
                    continue

                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    # Plain text token
                    acc["response_text"] += data_str
                    continue

                etype = event.get("type", "")

                if etype == "token":
                    acc["response_text"] += event.get("content", "")

                elif etype in ("telemetry", "devhud", "metrics"):
                    # Extract all useful state fields from telemetry event
                    tdata = event.get("data", event)
                    acc["telemetry"] = tdata

                    # Flatten common fields
                    for field_name in (
                        "intent", "generation_mode", "answer_confidence",
                        "has_hallucination_risk", "needs_retrieval",
                        "retrieval_confidence", "document_relevance",
                        "sub_questions",
                    ):
                        if field_name in tdata:
                            acc[field_name] = tdata[field_name]

                    if "execution_trace" in tdata:
                        acc["execution_trace"] = tdata["execution_trace"]
                    if "tool_execution_results" in tdata:
                        acc["tool_execution_results"] = tdata["tool_execution_results"]
                    if "web_status" in tdata:
                        acc["web_status"] = tdata["web_status"]

                elif etype == "error":
                    raise RuntimeError(f"Backend error: {event.get('message', event)}")

                elif etype == "done":
                    break

                else:
                    # Fallback: unknown event type — try to grab content
                    if "content" in event:
                        acc["response_text"] += str(event["content"])

        acc["latency_ms"] = int((time.monotonic() - t0) * 1000)
        return acc


# ─────────────────────────────────────────────────────────────────────────────
#  BenchmarkRunner
# ─────────────────────────────────────────────────────────────────────────────

class BenchmarkRunner:
    """Orchestrates concurrent benchmark test case execution."""

    def __init__(
        self,
        config: BenchmarkConfig,
        scorer_fn: Callable[[dict, dict], dict],
    ) -> None:
        self.config    = config
        self.scorer_fn = scorer_fn

    async def run_case(
        self,
        case: dict,
        client: OmniClient,
        token: str,
        model: str = "gemini-2.0-flash",
        capability: str = "unknown",
    ) -> EvalResult:
        """Run a single test case and return an EvalResult."""
        case_id   = case.get("id", "unknown")
        query     = case.get("question") or case.get("query") or case.get("message", "")
        intent    = case.get("intent", "")
        latency   = 0
        error_msg = None
        score     = 0.0
        raw_m     = {}
        response  = {}

        try:
            # Override intent via extra context if needed
            extra = {}
            if intent:
                extra["X-Bench-Intent-Hint"] = intent

            response  = await client.stream_chat(
                message=query,
                token=token,
                model=model,
                extra_headers=extra,
            )
            latency   = response.get("latency_ms", 0)

            # Score
            scored    = self.scorer_fn(case, response)
            score     = float(scored.get("score", 0.0))
            raw_m     = scored.get("raw_metrics", {})

        except Exception as exc:  # noqa: BLE001
            error_msg = str(exc)
            logger.warning("Case %s failed: %s", case_id, exc)

        return EvalResult(
            case_id         = case_id,
            capability      = capability,
            score           = score,
            raw_metrics     = raw_m,
            latency_ms      = latency,
            trace           = {"execution_trace": response.get("execution_trace", [])},
            intent_detected = response.get("intent", ""),
            generation_mode = response.get("generation_mode", ""),
            error           = error_msg,
        )

    async def run_suite(
        self,
        cases: List[dict],
        capability: str,
        concurrency: int = 4,
        model: str = "gemini-2.0-flash",
    ) -> SuiteResult:
        """Run all cases concurrently (up to `concurrency` at once)."""
        sem     = asyncio.Semaphore(concurrency)
        results: List[EvalResult] = []

        async with OmniClient(self.config) as client:
            token = await client.authenticate()

            async def _run_one(case: dict) -> EvalResult:
                async with sem:
                    return await self.run_case(
                        case, client, token,
                        model=model,
                        capability=capability,
                    )

            tasks   = [asyncio.create_task(_run_one(c)) for c in cases]
            total   = len(tasks)

            for i, fut in enumerate(asyncio.as_completed(tasks), 1):
                result = await fut
                results.append(result)
                status = "✓" if result.passed(self.config.pass_threshold) else "✗"
                print(
                    f"  [{i:>3}/{total}] {status} {result.case_id:<20}"
                    f"  score={result.score:.3f}  {result.latency_ms}ms"
                    + (f"  ERR: {result.error[:60]}" if result.error else "")
                )

        return SuiteResult.from_results(
            capability,
            results,
            pass_threshold=self.config.pass_threshold,
        )


# ─────────────────────────────────────────────────────────────────────────────
#  I/O helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_dataset(path: Path) -> List[dict]:
    """Read a JSONL benchmark dataset file."""
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    cases = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("Skipping line %d in %s: %s", lineno, path.name, exc)

    logger.info("Loaded %d cases from %s", len(cases), path.name)
    return cases


def save_results(suite: SuiteResult, output_path: Path) -> None:
    """
    Write results to disk:
      <output_path>         — JSONL with one EvalResult per line
      <output_path>.summary.json — aggregated summary
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write per-case JSONL
    with output_path.open("w", encoding="utf-8") as fh:
        for r in suite.cases:
            fh.write(json.dumps(r.to_dict()) + "\n")

    # Write summary JSON
    summary_path = output_path.with_suffix("").with_suffix(".summary.json")
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(suite.summary_dict(), fh, indent=2)

    print(f"\n  Results → {output_path}")
    print(f"  Summary → {summary_path}")
