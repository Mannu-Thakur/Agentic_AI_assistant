"""
app/versioning/version_config.py — Centralized version tracking for all configurable components.

Every production-relevant component has a version string so changes are traceable.
Versions are embedded in telemetry records and evaluation results.

Increment a version when:
  - Prompt templates change meaningfully
  - Routing logic changes
  - Embedding model changes
  - Evaluation thresholds change
  - Retrieval strategy changes

This ensures every request is associated with the exact configuration that produced it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class PlatformVersions:
    """Immutable snapshot of all component versions."""
    platform: str = "2.0.0"
    agent_graph: str = "3.0.0"       # LangGraph agent (Phase 3)
    prompt: str = "3.1.0"            # System prompts and few-shot examples
    routing: str = "1.0.0"           # LLM/SLM routing logic
    embedding: str = "1.0.0"         # Embedding model (HuggingFace all-MiniLM)
    retrieval: str = "3.0.0"         # Hybrid BM25+dense+reranker pipeline
    evaluation: str = "1.0.0"        # Evaluation framework
    knowledge_graph: str = "1.0.0"   # Neo4j GraphRAG pipeline
    drift_detection: str = "1.0.0"   # Drift detection thresholds

    def to_dict(self) -> Dict[str, str]:
        return {
            "platform": self.platform,
            "agent_graph": self.agent_graph,
            "prompt": self.prompt,
            "routing": self.routing,
            "embedding": self.embedding,
            "retrieval": self.retrieval,
            "evaluation": self.evaluation,
            "knowledge_graph": self.knowledge_graph,
            "drift_detection": self.drift_detection,
        }

    def to_telemetry_fields(self) -> Dict[str, str]:
        """Return subset of versions for inclusion in per-request telemetry."""
        return {
            "prompt_version": self.prompt,
            "routing_version": self.routing,
            "embedding_version": self.embedding,
        }


# Global singleton — import this everywhere
VERSIONS = PlatformVersions()
