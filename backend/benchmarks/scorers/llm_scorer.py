"""
benchmarks/scorers/llm_scorer.py — Scorer for LLM QA capability.

Evaluates:
  - ROUGE-L F1 (lexical recall and precision)
  - Token Overlap F1
  - Keyword Coverage (% of expected key terms present)
  - Hallucination Risk penalty (from evidence_checker)
  - Length & substantive quality score
"""

from __future__ import annotations

import re
import string
from typing import Any

# Try rouge_score, fallback gracefully to token-level metrics if not installed
try:
    from rouge_score import rouge_scorer
    _ROUGE_AVAILABLE = True
    _scorer = rouge_scorer.RougeScorer(["rougeL"], use_stemmer=True)
except ImportError:
    _ROUGE_AVAILABLE = False
    _scorer = None


def _tokenize(text: str) -> list[str]:
    """Lowercase and extract words without punctuation."""
    text = text.lower()
    for p in string.punctuation:
        text = text.replace(p, " ")
    return [w for w in text.split() if w]


def _compute_token_f1(pred: str, ref: str) -> float:
    """Compute token-level precision, recall, and F1."""
    p_tokens = _tokenize(pred)
    r_tokens = _tokenize(ref)
    if not p_tokens or not r_tokens:
        return 0.0
    common = set(p_tokens) & set(r_tokens)
    if not common:
        return 0.0
    precision = len(common) / len(p_tokens)
    recall = len(common) / len(r_tokens)
    return (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0


def _compute_keyword_coverage(pred: str, ref: str) -> float:
    """Fraction of significant content words in ref found in pred."""
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "and", "or", "in",
        "on", "at", "to", "for", "of", "with", "by", "that", "this", "it",
        "as", "from", "be", "have", "has", "had", "not", "but", "what", "how"
    }
    r_words = [w for w in _tokenize(ref) if w not in stop_words and len(w) > 2]
    if not r_words:
        return 1.0
    pred_lower = pred.lower()
    matched = sum(1 for w in r_words if w in pred_lower)
    return matched / len(r_words)


def score_llm_qa(case: dict[str, Any], response_data: dict[str, Any]) -> dict[str, Any]:
    """
    Score a normal LLM response against expected ground-truth.

    Returns:
      {
        "score": float (0.0 to 1.0),
        "raw_metrics": {...}
      }
    """
    expected = case.get("expected_answer", "")
    pred = response_data.get("response_text", "").strip()

    if not pred:
        return {
            "score": 0.0,
            "raw_metrics": {
                "rouge_l_f1": 0.0,
                "token_f1": 0.0,
                "keyword_coverage": 0.0,
                "response_length": 0,
                "has_hallucination_risk": True,
                "answer_confidence": 0.0,
            },
        }

    # 1. ROUGE-L
    rouge_l_f1 = 0.0
    if _ROUGE_AVAILABLE and _scorer:
        scores = _scorer.score(expected, pred)
        rouge_l_f1 = scores["rougeL"].fmeasure
    else:
        rouge_l_f1 = _compute_token_f1(pred, expected)

    # 2. Token overlap F1
    token_f1 = _compute_token_f1(pred, expected)

    # 3. Keyword coverage
    keyword_cov = _compute_keyword_coverage(pred, expected)

    # 4. Hallucination indicators from Omni state
    has_hallucination_risk = response_data.get("has_hallucination_risk", False)
    answer_conf = float(response_data.get("answer_confidence", 0.85) or 0.85)

    # 5. Length appropriateness
    length_bonus = 1.0 if len(pred) >= 50 else (len(pred) / 50.0)

    # Composite normalized score (0.0 - 1.0)
    score = (
        0.35 * rouge_l_f1
        + 0.25 * token_f1
        + 0.25 * keyword_cov
        + 0.10 * (1.0 - (0.4 if has_hallucination_risk else 0.0))
        + 0.05 * length_bonus
    )
    score = min(max(score, 0.0), 1.0)

    return {
        "score": round(score, 4),
        "raw_metrics": {
            "rouge_l_f1": round(rouge_l_f1, 4),
            "token_f1": round(token_f1, 4),
            "keyword_coverage": round(keyword_cov, 4),
            "response_length": len(pred),
            "has_hallucination_risk": has_hallucination_risk,
            "answer_confidence": round(answer_conf, 3),
        },
    }
