"""
app/agents/web_research_agent.py — Web Research + Citations Agent

Uses the existing unified_web_search() which returns SearchResult objects,
synthesises a cited Markdown report, and saves it as an artifact.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.agents.registry import BaseAgent, AgentResult, agent_registry
from app.agents.artifacts import artifact_store
from app.agents.node_helpers import call_llm_simple

logger = logging.getLogger("agents.web_research")

SYNTHESIS_SYSTEM = (
    "You are an expert research analyst. Write a clear, well-structured Markdown report. "
    "Every factual claim MUST cite a source using [1], [2], etc. from the provided context. "
    "Never fabricate information not present in the sources."
)


@agent_registry.register("web_research")
class WebResearchAgent(BaseAgent):
    """
    Searches the web using unified_web_search (Tavily/Exa/DuckDuckGo),
    synthesises the results into a grounded cited report, and saves it
    as a Markdown artifact.
    """

    name = "web_research"
    description = (
        "Searches the internet for up-to-date information and produces a grounded "
        "research report with inline citations [1][2][3]. Best for factual questions, "
        "current events, and topics requiring external sources."
    )
    capabilities = [
        "web_search", "fact_finding", "citations",
        "current_events", "research_report",
    ]

    async def run(
        self,
        task_input: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        query      = task_input.get("query", "")
        user_id    = task_input.get("user_id", "anon")
        session_id = task_input.get("session_id", "default")
        from app.core.config import settings
        model      = task_input.get("active_model", settings.GEMINI_MODEL)
        api_keys   = task_input.get("api_keys", {})
        max_results = task_input.get("max_results", 6)

        logger.info(f"[WebResearchAgent] query={query[:60]!r}")

        # ── Step 1: Web search ────────────────────────────────────────────────
        from app.services.web_search import unified_web_search

        search_results = []
        try:
            raw_results = await unified_web_search(
                query=query,
                api_keys=api_keys,
                max_results=max_results,
            )
            # unified_web_search returns SearchResult objects; access attrs or dict
            for r in raw_results:
                if hasattr(r, "title"):
                    search_results.append({
                        "title":   r.title,
                        "url":     r.url,
                        "content": r.content or r.snippet or "",
                        "source":  getattr(r, "source", "web"),
                    })
                elif isinstance(r, dict):
                    search_results.append({
                        "title":   r.get("title", ""),
                        "url":     r.get("url", ""),
                        "content": r.get("content") or r.get("snippet", ""),
                        "source":  r.get("source", "web"),
                    })
        except Exception as exc:
            logger.warning(f"[WebResearchAgent] Search failed: {exc}")

        if not search_results:
            # Graceful fallback: LLM-only answer (no external sources)
            try:
                answer = await call_llm_simple(
                    prompt=f"Answer this question based on your knowledge:\n\n{query}",
                    model=model,
                    api_keys=api_keys,
                    system="Answer concisely with your best knowledge. Note if you are uncertain.",
                )
                return AgentResult(
                    agent_name=self.name,
                    success=True,
                    content=f"*(No external sources found — LLM knowledge only)*\n\n{answer}",
                    sources=[],
                    metadata={"mode": "llm_fallback"},
                )
            except Exception as exc:
                return AgentResult(
                    agent_name=self.name,
                    success=False,
                    error=f"Search and LLM fallback both failed: {exc}",
                )

        # ── Step 2: Build context with citation numbers ────────────────────────
        context_parts = []
        sources: List[Dict] = []
        for i, r in enumerate(search_results, start=1):
            context_parts.append(
                f"[{i}] **{r['title']}** ({r['url']})\n{r['content'][:600]}"
            )
            sources.append({
                "index":    i,
                "title":    r["title"],
                "url":      r["url"],
                "filename": r["title"][:40],
                "content":  r["content"][:300],
                "used":     True,
                "source":   r["source"],
            })

        context_block = "\n\n".join(context_parts)
        synthesis_prompt = (
            f"Research question: {query}\n\n"
            f"Sources:\n{context_block}\n\n"
            "Write a comprehensive, well-structured Markdown research report. "
            "Use [1], [2], etc. for every factual claim. "
            "End with a ## Sources section listing all references."
        )

        # ── Step 3: LLM synthesis ─────────────────────────────────────────────
        try:
            report_md = await call_llm_simple(
                prompt=synthesis_prompt,
                model=model,
                api_keys=api_keys,
                system=SYNTHESIS_SYSTEM,
                temperature=0.2,
                max_tokens=5000,
            )
        except Exception as exc:
            return AgentResult(
                agent_name=self.name,
                success=False,
                error=f"LLM synthesis failed: {exc}",
                sources=sources,
            )

        # ── Step 4: Save artifact ─────────────────────────────────────────────
        artifact_info: Optional[Dict] = None
        try:
            art = await artifact_store.create(
                artifact_type="report",
                content=report_md,
                agent=self.name,
                user_id=user_id,
                session_id=session_id,
                description=query[:120],
                metadata={
                    "query":          query,
                    "sources_count":  len(sources),
                    "search_results": len(search_results),
                },
            )
            artifact_info = art.to_dict()
        except Exception as exc:
            logger.warning(f"[WebResearchAgent] Artifact save failed: {exc}")

        return AgentResult(
            agent_name=self.name,
            success=True,
            content=report_md,
            sources=sources,
            artifacts=[artifact_info] if artifact_info else [],
            metadata={
                "query":         query,
                "sources_count": len(sources),
                "mode":          "web_search",
            },
        )
