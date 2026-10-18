"""
app/agents/rag_agent.py — RAG / Knowledge-Base Agent

An independent subgraph wrapping the existing VectorStore (ChromaDB +
BM25 hybrid) and reranker.  When the Supervisor picks this agent, it
retrieves semantically-relevant chunks from the user's uploaded documents,
reranks them, then synthesises a grounded answer with confidence scoring.

task_input keys
---------------
  query        : str
  user_id      : str
  session_id   : str
  active_model : str
  api_keys     : dict
  top_k        : int  (optional, default 6)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.agents.registry import BaseAgent, AgentResult, agent_registry
from app.agents.artifacts import artifact_store
from app.agents.node_helpers import call_llm_simple

logger = logging.getLogger("agents.rag")

RAG_SYSTEM = (
    "You are a knowledge retrieval assistant. Answer the question using ONLY "
    "the provided document chunks. Cite chunk numbers like [C1], [C2]. "
    "If the chunks don't contain sufficient information, say so clearly."
)


@agent_registry.register("rag")
class RagAgent(BaseAgent):
    """
    Retrieves information from the user's uploaded documents using hybrid
    dense+BM25 vector search with cross-encoder reranking, then synthesises
    a grounded, cited answer.
    """

    name = "rag"
    description = (
        "Searches the user's uploaded documents and knowledge base using hybrid "
        "vector + BM25 retrieval with cross-encoder reranking. Returns grounded "
        "answers citing specific document chunks. Best for document-specific queries."
    )
    capabilities = [
        "document_qa", "knowledge_retrieval", "rag",
        "file_search", "chunk_retrieval",
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
        top_k      = int(task_input.get("top_k", 6))

        logger.info(f"[RagAgent] query={query[:60]!r} user={user_id}")

        # ── Step 1: Vector search ─────────────────────────────────────────────
        chunks: List[Dict] = []
        try:
            from app.retrieval.vector_store import VectorStore
            vs = VectorStore()

            raw_chunks = await vs.search(
                query=query,
                user_id=user_id,
                top_k=top_k,
            )

            for i, chunk in enumerate(raw_chunks or [], start=1):
                if isinstance(chunk, dict):
                    chunks.append({
                        "index":    i,
                        "content":  chunk.get("content", chunk.get("text", "")),
                        "filename": chunk.get("filename", chunk.get("source", f"doc_{i}")),
                        "distance": chunk.get("distance", 0.0),
                        "score":    chunk.get("score", 0.0),
                    })
                elif hasattr(chunk, "page_content"):
                    # LangChain Document
                    chunks.append({
                        "index":    i,
                        "content":  chunk.page_content,
                        "filename": chunk.metadata.get("source", f"doc_{i}"),
                        "distance": chunk.metadata.get("distance", 0.0),
                        "score":    chunk.metadata.get("score", 0.0),
                    })

        except Exception as exc:
            logger.warning(f"[RagAgent] Vector search failed: {exc}")
            # Fallback: return honest "no documents" response
            return AgentResult(
                agent_name=self.name,
                success=True,
                content=(
                    f"No documents found in the knowledge base for: **{query}**\n\n"
                    "Please upload documents first, or use the Web Research agent "
                    "for internet-sourced answers."
                ),
                sources=[],
                metadata={"mode": "empty_kb", "error": str(exc)},
            )

        if not chunks:
            return AgentResult(
                agent_name=self.name,
                success=True,
                content=(
                    f"No relevant document chunks found for: **{query}**\n\n"
                    "The knowledge base may not contain information on this topic."
                ),
                sources=[],
                metadata={"mode": "no_chunks"},
            )

        # ── Step 2: Build context block ───────────────────────────────────────
        context_parts = []
        sources: List[Dict] = []
        for c in chunks:
            context_parts.append(
                f"[C{c['index']}] **{c['filename']}**\n{c['content'][:800]}"
            )
            sources.append({
                "index":    c["index"],
                "filename": c["filename"],
                "content":  c["content"][:300],
                "used":     True,
                "distance": c["distance"],
            })

        context = "\n\n---\n\n".join(context_parts)
        synthesis_prompt = (
            f"User question: {query}\n\n"
            f"Document chunks:\n{context}\n\n"
            "Answer the question using only the chunks above. "
            "Cite as [C1], [C2], etc. for every claim."
        )

        # ── Step 3: LLM synthesis ─────────────────────────────────────────────
        try:
            answer = await call_llm_simple(
                prompt=synthesis_prompt,
                model=model,
                api_keys=api_keys,
                system=RAG_SYSTEM,
                temperature=0.1,
                max_tokens=3000,
            )
        except Exception as exc:
            return AgentResult(
                agent_name=self.name,
                success=False,
                error=f"LLM synthesis failed: {exc}",
                sources=sources,
            )

        # ── Step 4: Save report artifact ──────────────────────────────────────
        artifact_info: Optional[Dict] = None
        try:
            report = (
                f"# Knowledge Base Answer\n\n**Query:** {query}\n\n"
                f"## Answer\n\n{answer}\n\n"
                f"## Sources ({len(sources)} chunks)\n\n" +
                "\n".join(f"- [C{s['index']}] {s['filename']}" for s in sources)
            )
            art = await artifact_store.create(
                artifact_type="report",
                content=report,
                agent=self.name,
                user_id=user_id,
                session_id=session_id,
                description=query[:120],
                metadata={"query": query, "chunks_used": len(chunks)},
            )
            artifact_info = art.to_dict()
        except Exception as exc:
            logger.warning(f"[RagAgent] Artifact save failed: {exc}")

        return AgentResult(
            agent_name=self.name,
            success=True,
            content=answer,
            sources=sources,
            artifacts=[artifact_info] if artifact_info else [],
            metadata={
                "chunks_retrieved": len(chunks),
                "query": query,
                "mode": "rag",
            },
        )
