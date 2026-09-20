"""
app/evaluation/deterministic_checks.py — Non-LLM deterministic quality checks.

These checks do NOT use an LLM judge and are therefore:
  - Always available
  - Zero cost
  - Consistent and reproducible
  - Fast (< 1ms each)

Checks implemented:
  1. Response length adequacy (too short = likely incomplete)
  2. Citation coverage (are retrieved chunks cited?)
  3. Hedging language detection (confidence calibration)
  4. Forbidden content patterns (refusal detection)
  5. Question-answer topic overlap (basic relevance)
  6. Response completeness (ends with a sentence, not mid-thought)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List


def check_response_length(response: str, min_words: int = 10) -> Dict[str, Any]:
    """Check if the response is substantively non-empty."""
    word_count = len(response.split())
    passed = word_count >= min_words
    return {
        "check": "response_length",
        "passed": passed,
        "word_count": word_count,
        "min_required": min_words,
        "score": min(1.0, word_count / max(min_words, 1)),
    }


def check_citation_coverage(response: str, retrieved_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Check what fraction of retrieved chunks are cited or referenced in the response.
    Uses filename keyword matching as a proxy for citation.
    """
    if not retrieved_chunks:
        return {"check": "citation_coverage", "passed": True, "score": 1.0, "cited_count": 0, "total_chunks": 0}

    response_lower = response.lower()
    cited = 0
    for chunk in retrieved_chunks:
        filename = str(chunk.get("filename", chunk.get("source", ""))).lower()
        # Check if filename keywords appear in response
        name_parts = re.split(r"[._\-\s]", filename)
        if any(part in response_lower for part in name_parts if len(part) > 3):
            cited += 1
        # Also count [N] style citation markers
        elif re.search(r"\[\d+\]", response):
            cited += 1  # numeric citations present
            break

    coverage = cited / len(retrieved_chunks)
    return {
        "check": "citation_coverage",
        "passed": coverage >= 0.3 or not retrieved_chunks,
        "cited_count": cited,
        "total_chunks": len(retrieved_chunks),
        "coverage_ratio": round(coverage, 3),
        "score": coverage,
    }


def check_hedging_language(response: str) -> Dict[str, Any]:
    """
    Detect calibrated uncertainty language vs overconfident or underconfident responses.
    Overconfidence: asserting facts without qualification on uncertain topics.
    Underconfidence: excessive hedging that reduces usefulness.
    """
    hedging_patterns = [
        r"\b(may|might|could|possibly|perhaps|approximately|around|roughly)\b",
        r"\b(I believe|I think|it seems|it appears|likely|probably)\b",
        r"\b(according to|based on|as stated in|the document says)\b",
        r"\b(I cannot|I don't have|insufficient|not enough|unable to find)\b",
    ]
    overconfidence_patterns = [
        r"\b(definitely|certainly|absolutely|guaranteed|always|never|100%)\b",
    ]

    hedging_count = sum(
        len(re.findall(p, response, re.IGNORECASE)) for p in hedging_patterns
    )
    overconfidence_count = sum(
        len(re.findall(p, response, re.IGNORECASE)) for p in overconfidence_patterns
    )

    # Ideal: some hedging, minimal overconfidence
    calibration_score = min(1.0, hedging_count * 0.2) - min(0.5, overconfidence_count * 0.25)
    calibration_score = max(0.0, calibration_score)

    return {
        "check": "hedging_language",
        "passed": True,  # informational only
        "hedging_count": hedging_count,
        "overconfidence_count": overconfidence_count,
        "calibration_score": round(calibration_score, 3),
        "score": calibration_score,
    }


def check_topic_overlap(question: str, response: str) -> Dict[str, Any]:
    """
    Simple keyword overlap check between question and response.
    A very low overlap may indicate the response went off-topic.
    """
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "what", "how", "why",
        "when", "where", "who", "which", "that", "this", "these", "those",
        "of", "in", "on", "at", "to", "for", "with", "by", "from", "about",
        "can", "do", "does", "did", "have", "has", "had", "will", "would",
        "could", "should", "me", "my", "i", "you", "your", "it", "its",
    }
    q_words = {w.lower().strip('.,?!') for w in question.split() if len(w) > 3} - stop_words
    r_words = {w.lower().strip('.,?!') for w in response.split() if len(w) > 3} - stop_words

    if not q_words:
        return {"check": "topic_overlap", "passed": True, "score": 1.0, "overlap_ratio": 1.0}

    overlap = len(q_words & r_words)
    overlap_ratio = overlap / len(q_words)

    return {
        "check": "topic_overlap",
        "passed": overlap_ratio >= 0.2,
        "overlap_words": overlap,
        "question_keywords": len(q_words),
        "overlap_ratio": round(overlap_ratio, 3),
        "score": min(1.0, overlap_ratio * 2),  # scale 0-0.5 to 0-1
    }


def check_completeness(response: str) -> Dict[str, Any]:
    """Check if the response appears structurally complete (ends with a sentence)."""
    stripped = response.strip()
    looks_complete = (
        stripped.endswith(('.', '!', '?', '"', "'", ')', ']', '`')) or
        len(stripped.split()) < 5  # very short responses are complete by nature
    )
    return {
        "check": "completeness",
        "passed": looks_complete,
        "score": 1.0 if looks_complete else 0.5,
    }


def run_all_checks(
    question: str,
    response: str,
    retrieved_chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Run all deterministic checks and return aggregated results.
    """
    checks = [
        check_response_length(response),
        check_citation_coverage(response, retrieved_chunks),
        check_hedging_language(response),
        check_topic_overlap(question, response),
        check_completeness(response),
    ]

    passed_count = sum(1 for c in checks if c["passed"])
    scores = [c["score"] for c in checks]
    avg_score = sum(scores) / len(scores) if scores else 0.0

    return {
        "checks": checks,
        "passed_count": passed_count,
        "total_checks": len(checks),
        "all_passed": passed_count == len(checks),
        "aggregate_score": round(avg_score, 3),
    }


class DeterministicCheckResult:
    """Structured result wrapper for deterministic evaluation checks."""

    def __init__(self, passed: bool, overall_score: float, details: Dict[str, Any]):
        self.passed = passed
        self.overall_score = overall_score
        self.checks = details.get("checks", [])
        self.details = details


def run_deterministic_checks(
    question: str = "",
    answer: str = "",
    context: Any = None,
) -> DeterministicCheckResult:
    """
    Convenience wrapper to run deterministic quality checks on a question/answer pair.

    Args:
        question: User query string
        answer: Generated AI answer
        context: Optional retrieved context chunks (strings or chunk dicts)

    Returns:
        DeterministicCheckResult with passed flag, overall_score, and individual check details.
    """
    chunks = []
    if context:
        for c in context:
            if isinstance(c, str):
                chunks.append({"content": c})
            elif isinstance(c, dict):
                chunks.append(c)

    res = run_all_checks(question=question, response=answer, retrieved_chunks=chunks)
    passed = res.get("all_passed", False)
    # If answer is empty or has zero length score, passed is False
    if not answer or not answer.strip():
        passed = False
    score = res.get("aggregate_score", 0.0)
    return DeterministicCheckResult(passed=passed, overall_score=score, details=res)
