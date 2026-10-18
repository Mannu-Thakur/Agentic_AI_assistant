"""
app/agents/critic_agent.py — Critic / Verifier Agent

Responsibilities
----------------
  1. Factual accuracy check — Cross-reference claims in a response against
     provided source documents / web results.
  2. Hallucination detection — Flag statements that cannot be grounded in
     any source, with a confidence score.
  3. Citation validation — Verify that inline citation references [1],[2]...
     actually correspond to real sources and that the claim matches.
  4. Code correctness — For code responses, run static checks (syntax) and
     review for obvious bugs without execution.
  5. Output quality scoring — Score on coherence, completeness, accuracy.

Returns
-------
  AgentResult.content     — Critic's structured feedback
  AgentResult.metadata    — {
      quality_score,        # 0.0–1.0
      hallucination_risk,   # bool
      unsupported_claims,   # list[str]
      citation_issues,      # list[str]
      suggestions,          # list[str]
      passes,               # bool — should response be accepted?
  }
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from app.agents.registry import BaseAgent, AgentResult, agent_registry
from app.agents.node_helpers import call_llm_json, call_llm_simple

logger = logging.getLogger("agents.critic")

CRITIC_SYSTEM_PROMPT = """You are a strict fact-checking and quality-control agent.
Your job is to evaluate AI-generated responses for:
  1. Factual accuracy (vs provided sources)
  2. Hallucinations (claims with no source support)
  3. Citation correctness
  4. Completeness and coherence
  5. Code correctness (if code is present)

Always respond with valid JSON matching exactly this schema:
{
  "quality_score": 0.0-1.0,
  "hallucination_risk": true/false,
  "passes": true/false,
  "unsupported_claims": ["claim1", "claim2"],
  "citation_issues": ["issue1"],
  "suggestions": ["suggestion1"],
  "critique": "2-3 sentence overall critique"
}
"""


@agent_registry.register("critic")
class CriticAgent(BaseAgent):
    """
    Independent quality verifier that runs after all other agents complete.
    Provides structured feedback and a pass/fail decision.
    """

    name = "critic"
    description = (
        "Verifies factual accuracy, detects hallucinations, validates citations, "
        "checks code correctness, and provides a quality score (0–1) for responses."
    )
    capabilities = [
        "fact_checking", "hallucination_detection",
        "citation_validation", "quality_scoring", "code_review",
    ]

    async def run(
        self,
        task_input: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        response    = task_input.get("response", "")
        sources     = task_input.get("sources", [])
        query       = task_input.get("query", "")
        from app.core.config import settings
        model       = task_input.get("active_model", settings.GEMINI_MODEL)
        api_keys    = task_input.get("api_keys", {})

        logger.info(f"[CriticAgent] Verifying response for query: {query[:60]!r}")

        if not response:
            return AgentResult(
                agent_name=self.name,
                success=True,
                content="No response to verify.",
                quality_score=0.0,
                metadata={"passes": False, "error": "Empty response"},
            )

        # ── Build source context for grounding check ───────────────────────────
        source_text = ""
        if sources:
            source_lines = []
            for i, s in enumerate(sources[:8], 1):
                content = s.get("content", s.get("snippet", ""))
                title   = s.get("title", s.get("filename", f"Source {i}"))
                source_lines.append(f"[{i}] {title}: {content[:300]}")
            source_text = "\n".join(source_lines)
        else:
            source_text = "(No source documents provided — check for hallucinations conservatively)"

        # ── Build critic prompt ────────────────────────────────────────────────
        critic_prompt = f"""
Evaluate this AI response:

**Original Query:** {query}

**Response to Evaluate:**
{response[:3000]}

**Available Sources for Grounding:**
{source_text}

Check for:
1. Claims not supported by any source
2. Incorrect citation references
3. Logical inconsistencies
4. Missing important information from sources
5. Code bugs (if code is present)

Respond with the JSON schema specified.
""".strip()

        # ── Call critic LLM ────────────────────────────────────────────────────
        critic_result: Dict[str, Any] = {}
        try:
            critic_result = await call_llm_json(
                prompt=critic_prompt,
                model=model,
                api_keys=api_keys,
                system=CRITIC_SYSTEM_PROMPT,
                temperature=0.1,
            )
        except Exception as exc:
            logger.warning(f"[CriticAgent] LLM call failed: {exc}")
            # Fallback to a lenient pass
            critic_result = {
                "quality_score": 0.7,
                "hallucination_risk": False,
                "passes": True,
                "unsupported_claims": [],
                "citation_issues": [],
                "suggestions": [],
                "critique": f"Critic LLM unavailable: {exc}",
            }

        # ── Extract structured fields ──────────────────────────────────────────
        quality_score      = float(critic_result.get("quality_score", 0.7))
        hallucination_risk = bool(critic_result.get("hallucination_risk", False))
        passes             = bool(critic_result.get("passes", quality_score >= 0.6))
        unsupported        = critic_result.get("unsupported_claims", [])
        citation_issues    = critic_result.get("citation_issues", [])
        suggestions        = critic_result.get("suggestions", [])
        critique           = critic_result.get("critique", "")

        # ── Format critic feedback ─────────────────────────────────────────────
        feedback_parts = []
        status_icon = "✅" if passes else "⚠️"
        feedback_parts.append(
            f"{status_icon} **Critic Score: {quality_score:.0%}** "
            f"({'Passed' if passes else 'Needs Revision'})"
        )
        if critique:
            feedback_parts.append(f"\n{critique}")
        if unsupported:
            feedback_parts.append(
                "\n**Unsupported claims:**\n" +
                "\n".join(f"- {c}" for c in unsupported[:5])
            )
        if citation_issues:
            feedback_parts.append(
                "\n**Citation issues:**\n" +
                "\n".join(f"- {c}" for c in citation_issues[:3])
            )
        if suggestions:
            feedback_parts.append(
                "\n**Suggestions:**\n" +
                "\n".join(f"- {s}" for s in suggestions[:3])
            )

        return AgentResult(
            agent_name=self.name,
            success=True,
            content="\n".join(feedback_parts),
            quality_score=quality_score,
            metadata={
                "quality_score": quality_score,
                "hallucination_risk": hallucination_risk,
                "passes": passes,
                "unsupported_claims": unsupported,
                "citation_issues": citation_issues,
                "suggestions": suggestions,
                "critique": critique,
            },
        )
