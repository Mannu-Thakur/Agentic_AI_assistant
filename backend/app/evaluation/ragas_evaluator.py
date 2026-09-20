"""
app/evaluation/ragas_evaluator.py — RAGAS-based evaluation.

Integrates the RAGAS library for LLM-judge-based evaluation metrics:
  - Faithfulness: Is the answer grounded in the retrieved context?
  - Answer Relevancy: Does the answer address the question?
  - Context Recall: Does the context contain the information needed?

Falls back to a lightweight keyword-overlap proxy if RAGAS is not installed
or if no LLM key is available.

IMPORTANT: RAGAS requires an LLM API call per evaluation.
This module is only called when run_ragas=True in the evaluator.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.evaluation.ragas_evaluator")


async def run_ragas_evaluation(
    question: str,
    response: str,
    retrieved_chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Run RAGAS evaluation on a QA pair.

    Returns a dict with evaluation scores.
    Falls back to proxy metrics if RAGAS unavailable.
    """
    context_texts = [
        str(c.get("content", c.get("text", "")))
        for c in retrieved_chunks
        if c.get("content") or c.get("text")
    ]

    # ── Try RAGAS (requires: pip install ragas) ───────────────────────────────
    try:
        from ragas import evaluate
        from ragas.metrics import faithfulness, answer_relevancy, context_recall
        from datasets import Dataset
        from app.core.config import settings

        # Build RAGAS dataset
        data = {
            "question": [question],
            "answer": [response],
            "contexts": [context_texts] if context_texts else [["No context retrieved"]],
            "ground_truth": [response],  # We don't have ground truth — use response as proxy
        }
        dataset = Dataset.from_dict(data)

        # Configure RAGAS LLM (use cheapest available)
        ragas_llm = None
        if settings.OPENAI_API_KEY:
            from langchain_openai import ChatOpenAI
            ragas_llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY)
        elif settings.GROQ_API_KEY:
            from langchain_groq import ChatGroq
            ragas_llm = ChatGroq(model="llama-3.1-8b-instant", groq_api_key=settings.GROQ_API_KEY)

        if ragas_llm is None:
            raise ValueError("No LLM configured for RAGAS")

        result = evaluate(
            dataset,
            metrics=[faithfulness, answer_relevancy],
            llm=ragas_llm,
        )

        return {
            "available": True,
            "method": "ragas",
            "faithfulness": float(result["faithfulness"]),
            "answer_relevancy": float(result["answer_relevancy"]),
        }

    except ImportError:
        logger.info("[RAGAS] ragas library not installed — using proxy metrics")
    except Exception as e:
        logger.warning(f"[RAGAS] Evaluation failed: {e} — using proxy metrics")

    # ── Proxy metrics (no external LLM required) ──────────────────────────────
    return _proxy_evaluation(question, response, context_texts)


def _proxy_evaluation(
    question: str,
    response: str,
    context_texts: List[str],
) -> Dict[str, Any]:
    """
    Lightweight keyword-overlap proxy for RAGAS metrics.
    These are NOT as accurate as real RAGAS but are always available.
    """
    # Proxy faithfulness: what fraction of response key terms appear in context
    if context_texts:
        combined_context = " ".join(context_texts).lower()
        response_words = set(response.lower().split())
        stop_words = {"the", "a", "an", "is", "are", "was", "this", "that", "and", "or", "of", "in"}
        key_terms = response_words - stop_words
        if key_terms:
            supported = sum(1 for w in key_terms if w in combined_context)
            faithfulness_proxy = min(1.0, supported / len(key_terms))
        else:
            faithfulness_proxy = 0.5
    else:
        faithfulness_proxy = 0.0  # No context = can't be faithful

    # Proxy answer relevancy: overlap of question keywords in response
    q_words = set(question.lower().split()) - {"what", "how", "why", "when", "where", "who", "is", "are", "the", "a"}
    r_words = set(response.lower().split())
    relevancy_proxy = min(1.0, len(q_words & r_words) / max(len(q_words), 1))

    return {
        "available": True,
        "method": "proxy",
        "faithfulness": round(faithfulness_proxy, 3),
        "answer_relevancy": round(relevancy_proxy, 3),
        "note": "Proxy metrics — install ragas and configure LLM key for accurate RAGAS scores",
    }
