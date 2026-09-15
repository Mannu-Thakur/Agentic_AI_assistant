"""
benchmarks/config.py — Benchmark configuration for the Omni AI eval framework.

Reads from environment variables / .env file.
All paths are resolved relative to the backend/ directory.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# ── Resolve paths ────────────────────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent.parent      # backend/
_BENCH_DIR   = Path(__file__).resolve().parent             # backend/benchmarks/

# Load .env from the backend directory (then fall back to repo root)
load_dotenv(_BACKEND_DIR / ".env", override=False)
load_dotenv(_BACKEND_DIR.parent / ".env", override=False)


@dataclass
class BenchmarkConfig:
    """Central configuration for the Omni benchmark harness."""

    # ── Backend endpoints ─────────────────────────────────────────────────────
    base_url: str = "http://localhost:8000"
    auth_endpoint: str = "/api/v1/auth/login"
    chat_endpoint: str = "/api/v1/chat/stream"
    health_endpoint: str = "/api/v1/health"

    # ── Auth credentials (read from env) ─────────────────────────────────────
    bench_email: str = field(
        default_factory=lambda: os.getenv("BENCH_EMAIL", "test@example.com")
    )
    bench_password: str = field(
        default_factory=lambda: os.getenv("BENCH_PASSWORD", "testpassword123")
    )

    # ── Runtime settings ──────────────────────────────────────────────────────
    default_concurrency: int = 4
    default_timeout_s: int = 120
    default_model: str = "gemini-2.0-flash"

    # ── LLM judge ─────────────────────────────────────────────────────────────
    judge_model: str = "gemini-2.0-flash"
    judge_api_key: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "")
    )

    # ── Directory paths ───────────────────────────────────────────────────────
    results_dir: Path = field(default_factory=lambda: _BENCH_DIR / "results")
    datasets_dir: Path = field(default_factory=lambda: _BENCH_DIR / "datasets")
    report_dir: Path = field(default_factory=lambda: _BENCH_DIR / "report")

    # ── Per-capability sample limits (0 = run all) ────────────────────────────
    llm_qa_limit: int = 150
    mcp_limit: int = 80
    rag_limit: int = 100
    self_rag_limit: int = 60
    crag_limit: int = 60
    web_search_limit: int = 60
    agentic_limit: int = 50

    # ── Scoring thresholds ────────────────────────────────────────────────────
    pass_threshold: float = 0.60   # score >= this -> PASS
    excellent_threshold: float = 0.85

    def __post_init__(self) -> None:
        """Ensure output directories exist."""
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.datasets_dir.mkdir(parents=True, exist_ok=True)

    @property
    def auth_url(self) -> str:
        return self.base_url + self.auth_endpoint

    @property
    def chat_url(self) -> str:
        return self.base_url + self.chat_endpoint

    @property
    def health_url(self) -> str:
        return self.base_url + self.health_endpoint

    def capability_limit(self, capability: str) -> int:
        mapping = {
            "llm":      self.llm_qa_limit,
            "mcp":      self.mcp_limit,
            "rag":      self.rag_limit,
            "self_rag": self.self_rag_limit,
            "crag":     self.crag_limit,
            "web":      self.web_search_limit,
            "agentic":  self.agentic_limit,
        }
        return mapping.get(capability, 0)


def load_config() -> BenchmarkConfig:
    """Load config from environment variables."""
    return BenchmarkConfig()


# ── Published baselines for comparison in the report ─────────────────────────
PUBLISHED_BASELINES: dict[str, dict[str, float]] = {
    "llm": {
        "MMLU GPT-4o":          0.87,
        "MMLU Gemini-1.5-Pro":  0.85,
        "MMLU Llama-3-70B":     0.82,
    },
    "mcp": {
        "BFCL GPT-4o Tool Sel.":  0.85,
        "BFCL GPT-4o Arg F1":     0.78,
        "BFCL Claude-3.5 Sonnet": 0.81,
    },
    "rag": {
        "BM25-only Precision@5":  0.61,
        "Dense-only Precision@5": 0.69,
        "BM25 Faithfulness":      0.72,
    },
    "self_rag": {
        "Self-RAG paper routing": 0.82,
        "Always-retrieve naive":  0.50,
    },
    "crag": {
        "CRAG paper grading acc": 0.79,
        "Always-accept naive":    0.50,
    },
    "web": {
        "FreshQA GPT-4 coverage": 0.72,
        "FreshQA GPT-3.5":        0.58,
    },
    "agentic": {
        "AgentBench GPT-4":       0.49,
        "AgentBench GPT-3.5":     0.28,
        "No-planning baseline":   0.30,
    },
}

# ── Capability metadata ───────────────────────────────────────────────────────
CAPABILITY_META: dict[str, dict] = {
    "llm": {
        "name":        "LLM QA",
        "dataset":     "llm_qa.jsonl",
        "description": "Factuality, reasoning, MMLU-style multi-subject QA",
        "primary_metric": "rouge_l + keyword_coverage",
        "source_benchmarks": ["TruthfulQA", "MMLU", "HellaSwag", "OpenBookQA"],
    },
    "mcp": {
        "name":        "MCP / Tool Calling",
        "dataset":     "mcp_tool.jsonl",
        "description": "Tool selection accuracy and argument extraction on 6 MCP tools",
        "primary_metric": "tool_selection_accuracy",
        "source_benchmarks": ["BFCL", "ToolBench", "API-Bank"],
    },
    "rag": {
        "name":        "RAG",
        "dataset":     "rag.jsonl",
        "description": "Dense+BM25+RRF hybrid retrieval with cross-encoder reranking",
        "primary_metric": "context_precision + faithfulness (RAGAS)",
        "source_benchmarks": ["QASPER", "NarrativeQA", "QuALITY"],
    },
    "self_rag": {
        "name":        "Self-RAG",
        "dataset":     "self_rag.jsonl",
        "description": "Retrieval necessity routing accuracy and calibration",
        "primary_metric": "routing_accuracy",
        "source_benchmarks": ["PopQA", "Self-RAG paper eval set"],
    },
    "crag": {
        "name":        "CRAG",
        "dataset":     "crag.jsonl",
        "description": "Document relevance grading and web fallback precision",
        "primary_metric": "grading_accuracy",
        "source_benchmarks": ["KILT", "CRAG paper eval set"],
    },
    "web": {
        "name":        "Web Search",
        "dataset":     "web_search.jsonl",
        "description": "4-tier waterfall search: answer coverage and freshness",
        "primary_metric": "answer_coverage",
        "source_benchmarks": ["FreshQA", "ELI5 subset"],
    },
    "agentic": {
        "name":        "Agentic / Multi-Step",
        "dataset":     "agentic.jsonl",
        "description": "Multi-step planning, parallel tool execution, compound queries",
        "primary_metric": "step_completion_rate",
        "source_benchmarks": ["AgentBench", "HotpotQA", "MuSiQue"],
    },
}
