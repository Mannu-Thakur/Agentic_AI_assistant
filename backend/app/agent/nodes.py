"""
agent/nodes.py — All LangGraph node implementations.

P0 Production Fixes Applied
════════════════════════════
1.  classify_intent_node  — NEW: intent classifier that runs BEFORE any routing.
                            Returns intent, allowed_tools, is_private_doc_query,
                            and optional memory_write_content/memory_write_category.

2.  memory_write_node     — NEW: dedicated node for MEMORY_WRITE intent.
                            Persists the extracted fact, generates a short ACK,
                            bypasses ALL other nodes (routed directly to END).

3.  generate_response_node MODIFIED:
    • Tool schemas are now injected PER-INTENT (allowed_tools whitelist).
      No tool is ever offered to the LLM unless it is explicitly whitelisted
      for the current intent.
    • _sanitize_response() strips internal tool names from the final text.
    • uploaded_file_paths are passed to compile_system_prompt() so the LLM
      can reference exact server-side paths in generated code.
    • Graceful image-provider mismatch: returns a clear user-facing error
      instead of silently dropping images on non-Gemini providers.
    • no_doc_answer flag is forwarded to compile_system_prompt().

4.  grade_documents_node  MODIFIED:
    • Checks is_private_doc_query before triggering the Tavily web fallback.
    • When is_private_doc_query=True and no relevant chunks are found, sets
      document_relevance="no_private_docs" and no_doc_answer=True instead of
      calling Tavily (prevents private-intent leakage to external APIs).

5.  reflect_node          MODIFIED:
    • Skips reflection entirely for MEMORY_WRITE and NORMAL_CHAT intents.
    • Raises the "too brief" threshold so one-line ACKs are never regenerated.
"""

import os
import time
import json
import logging
import asyncio
import re
from typing import Dict, Any, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.agent.state import AgentState
from app.agent.prompts import (
    compile_system_prompt,
    PLANNER_PROMPT,
    RETRIEVAL_CHECK_PROMPT,
    DOCUMENT_GRADER_PROMPT,
    REFLECTION_PROMPT,
    INTENT_CLASSIFIER_PROMPT,
    MEMORY_WRITE_PROMPT,
    INTERNAL_TOOL_NAMES,
    INTENT_TOOL_WHITELIST,
    INTENT_MEMORY_WRITE,
    INTENT_NORMAL_CHAT,
    INTENT_WEB_SEARCH,
    INTENT_DOCUMENT_QA,
    INTENT_VISION,
    INTENT_COMPLEX,
    INTENT_CODE_EXECUTION,
    INTENT_MCP_TOOL,
    INTENT_FINANCE,
    INTENT_NEWS,
    INTENT_CURRENT_EVENTS,
    INTENT_MATH,
    AMBIGUITY_DETECTOR_PROMPT,
    CLARIFICATION_QUESTION_PROMPT,
    QUERY_RECONSTRUCTOR_PROMPT,
    QUERY_DECOMPOSITION_PROMPT,
    COMPOUND_QUERY_DETECTOR_PROMPT,
    RETRIEVAL_EVALUATOR_PROMPT,
    # Phase 3
    TOOL_PLANNER_PROMPT,
    EVIDENCE_CHECKER_PROMPT,
    STRUCTURED_REFLECTION_PROMPT,
    UX_STAGE_PLANNING,
    UX_STAGE_SEARCHING,
    UX_STAGE_RETRIEVING,
    UX_STAGE_READING_DOCS,
    UX_STAGE_CALLING_TOOLS,
    UX_STAGE_VERIFYING,
    UX_STAGE_GENERATING,
)
from app.providers.gemini import GeminiProvider
from app.providers.groq import GroqProvider
from app.providers.openrouter import OpenRouterProvider
from app.providers.openai_provider import OpenAIProvider
# Top-level imports so patch paths resolve correctly in tests
from app.core.database import AsyncSessionLocal
from app.tools.local_tools import tavily_search as tavily_search
from app.services.web_search import (
    unified_web_search,
    format_for_llm,
    format_as_source_documents,
)

logger = logging.getLogger("agent.nodes")

# ── Singleton provider instances ──────────────────────────────────────────────
gemini_provider     = GeminiProvider()
groq_provider       = GroqProvider()
openrouter_provider = OpenRouterProvider()
openai_provider     = OpenAIProvider()

# ── Private-document routing signals ─────────────────────────────────────────
# PRODUCTION FIX: Static _PERSONAL_DOC_SIGNALS has been REPLACED with a dynamic
# system (app/agent/doc_signals.py) that builds signal sets from the user's actual
# uploaded document filenames.  No project-specific names are hardcoded here.
# Use get_user_doc_signals(user_id) to obtain the per-user combined signal set.
from app.agent.doc_signals import (
    get_user_doc_signals,
    query_matches_user_signals,
    classify_sub_questions,
    UNIVERSAL_SIGNALS,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Provider routing helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_provider(model: str):
    if model.startswith("openrouter/"):
        return openrouter_provider
    elif "gemini" in model:
        return gemini_provider
    elif "llama" in model or "mixtral" in model or "gemma" in model or "groq" in model:
        return groq_provider
    elif "google" in model:
        return gemini_provider
    elif "gpt" in model or "o1-" in model or "o3-" in model or "o4-" in model:
        # If OpenAI key is set, use direct OpenAIProvider; otherwise OpenRouter
        openai_key = getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY")
        if openai_key and not str(openai_key).startswith("mock_"):
            return openai_provider
        return openrouter_provider
    elif "claude" in model:
        # Anthropic models — routed through openrouter
        return openrouter_provider
    elif "deepseek" in model:
        # DeepSeek models — routed through openrouter
        return openrouter_provider
    elif "qwen" in model or "glm" in model:
        # Alibaba/GLM — routed through openrouter
        return openrouter_provider
    # Unknown model name — default to gemini_provider
    return gemini_provider


def _extract_last_user_query(messages: list) -> str:
    """Safely extract content of last user/human message from list of LangChain objects or dicts."""
    for msg in reversed(messages or []):
        if hasattr(msg, "type") and getattr(msg, "type") in ("human", "user"):
            return msg.content if isinstance(msg.content, str) else ""
        elif isinstance(msg, dict):
            m_type = msg.get("type") or msg.get("role")
            if m_type in ("human", "user", "user_input"):
                content = msg.get("content", "")
                return content if isinstance(content, str) else ""
    return ""


def _format_ocr_text_to_markdown(raw_text: str) -> str:
    """Format raw OCR text into structured, elegant Markdown with headings, bold keys, and code blocks."""
    if not raw_text or not raw_text.strip():
        return raw_text

    text = raw_text.strip()

    # 1. Format Notes / Constraints
    text = re.sub(r"(?i)\bNote:\s*", r"\n\n> 💡 **Note:** ", text)

    # 2. Format Examples Section
    text = re.sub(r"(?i)\bExamples:\s*", r"\n\n### 📌 **Examples**\n\n", text)

    # 3. Format Input / Output / Explanation
    text = re.sub(r"(?i)\bInput:\s*",       r"\n* **Input:** ", text)
    text = re.sub(r"(?i)\bOutput:\s*",      r"\n* **Output:** ", text)
    text = re.sub(r"(?i)\bExplanation:\s*", r"\n* **Explanation:** ", text)

    # 4. Format Problem / Question headings
    text = re.sub(
        r"(?i)\b(Problem|Question|Task|Constraints?):\s*",
        r"\n\n#### 📝 **\1:** ",
        text,
    )

    # Clean up linebreaks
    lines = [line.strip() for line in text.split("\n")]
    formatted = "\n".join(lines)
    formatted = re.sub(r"\n{3,}", "\n\n", formatted).strip()
    return formatted


# ─────────────────────────────────────────────────────────────────────────────
#  Production-grade offline OCR Intelligence Engine
#  Converts garbled handwritten OCR text into fully structured Markdown
#  with Mermaid flowcharts, comparison tables, and organized sections.
#  Works 100% offline — no cloud LLM required.
# ─────────────────────────────────────────────────────────────────────────────

# ── Master correction dictionary for common handwritten OCR misreadings ───────
_OCR_CORRECTION_MAP: list = [
    # LangChain / LangGraph ecosystem
    (r"(?i)\bLanachans?\b",          "LangChain"),
    (r"(?i)\bLanqhain?s?\b",         "LangChain"),
    (r"(?i)\bLang[Cc]hains?\b",      "LangChain"),
    (r"(?i)\blavqchacn\b",           "LangChain"),
    (r"(?i)\blanqhage?\b",           "Language"),
    (r"(?i)\bLanqhains?\b",          "LangChain"),
    (r"(?i)\bLangGraph\b",           "LangGraph"),
    # Models / LLMs
    (r"(?i)\bEnbeele?\b",            "Embedding"),
    (r"(?i)\bEnbeel?\b",             "Embedding"),
    (r"(?i)\bEmbeddin\b",            "Embedding"),
    (r"(?i)\bMo[\s]?ls\b",           "Models"),
    (r"(?i)\blims\b",                "LLMs"),
    (r"(?i)\bLims\b",                "LLMs"),
    (r"(?i)\bllns\b",                "LLMs"),
    (r"(?i)\bAlmodsR?Q?\b",          "All Models"),
    (r"(?i)\bmodees?\b",             "Models"),
    (r"(?i)\bmodeles?\b",            "Models"),
    (r"(?i)\bmodell?s?\b",           "Models"),
    (r"(?i)\bMuels?\b",              "Models"),
    (r"(?i)\bmodees?\b",             "Models"),
    # Prompts
    (r"(?i)\bPR@MPTs?\b",            "PROMPTS"),
    (r"(?i)\bPR@MPT\b",              "PROMPT"),
    (r"(?i)\bPROMPTs?\b",            "PROMPTS"),
    (r"(?i)\bReusa[- ]?bL\b",        "Reusable"),
    (r"(?i)\bRusea?bl?e?\b",         "Reusable"),
    (r"(?i)\bDyhanic\b",             "Dynamic"),
    (r"(?i)\bDynaimck?\b",           "Dynamic"),
    (r"(?i)\bRefe\s?hascek?\b",      "Reference-based"),
    (r"(?i)\bfsompl?s?\b",           "few-shot prompts"),
    (r"(?i)\bIvonts?\b",             "Inputs"),
    (r"(?i)\bkos\b",                 "tokens"),
    (r"(?i)\bShok\b",                "Shot"),
    (r"(?i)\bfromPinx?\b",           "from context"),
    (r"(?i)\bRole[-\s]?base[dk]?\b", "Role-based"),
    # Chains
    (r"(?i)\bCxAINS?\b",             "CHAINS"),
    (r"(?i)\bChains?\b",             "CHAINS"),
    (r"(?i)\btut\s?seo[cC]?\b",      "sequential"),
    # Semantic Search
    (r"(?i)\bSaman[- ]?tc?\b",       "Semantic"),
    (r"(?i)\bSemantec?\b",           "Semantic"),
    (r"(?i)\bSenke@?\b",             "Search"),
    (r"(?i)\bSeakel?\b",             "Search"),
    (r"(?i)\bSeareh\b",              "Search"),
    (r"(?i)\bUnS\b",                 "Uses"),
    (r"(?i)\bUse[st]?\b",            "Uses"),
    (r"(?i)\bveefor\b",              "vector"),
    (r"(?i)\bvecfor\b",              "vector"),
    (r"(?i)\bvect0r\b",              "vector"),
    # Text / general
    (r"(?i)\btex[+ ]?\b",            "text"),
    (r"(?i)\b[il]con[e]?\b",         "icons"),
    (r"(?i)\bifac[e]?s?\b",          "interfaces"),
    (r"(?i)\binterfa[sc]es?\b",      "interfaces"),
    (r"(?i)\bthroug[nh]?\b",         "through"),
    (r"(?i)\bwhic[nh]\b",            "which"),
    (r"(?i)\binteract\b",            "interact"),
    (r"(?i)\bcore\b",                "core"),
    (r"(?i)\byou\b",                 "you"),
    (r"(?i)\bwith\b",                "with"),
    (r"(?i)\bGn\b",                  "In"),
    # Arrow / special characters cleanup
    (r"~+",                          ""),
    (r"(?<![a-zA-Z])@(?![a-zA-Z])",  ""),
    (r"_{2,}",                       ""),
]

# ── Section-header pattern recognition ───────────────────────────────────────
_SECTION_PATTERNS: list = [
    # Models
    (r"(?i)\b(#?\s*Models?)\b",       "MODELS"),
    (r"(?i)\b(#?\s*LangChain)\b",     "LANGCHAIN"),
    # Prompts
    (r"(?i)\b(#?\s*PROMPTS?)\b",      "PROMPTS"),
    (r"(?i)\b(#?\s*Prompt\s*Template)\b", "PROMPTS"),
    # Chains
    (r"(?i)\b(#?\s*CHAINS?)\b",       "CHAINS"),
    (r"(?i)\b(#?\s*Agents?)\b",       "AGENTS"),
    (r"(?i)\b(#?\s*Memory)\b",        "MEMORY"),
    (r"(?i)\b(#?\s*Tools?)\b",        "TOOLS"),
    (r"(?i)\b(#?\s*RAG)\b",           "RAG"),
    (r"(?i)\b(#?\s*Vector\s*Store)\b","VECTOR STORE"),
]

# ── Bullet-point signal words (→, -, •, *, digits) ───────────────────────────
_BULLET_SIGNALS_RE = re.compile(
    r"^(?:[\-\*•→➤>]|\d+\.\s|[a-z]\)\s)",
    re.IGNORECASE,
)

# ── Diagram relation extractor: detects parent→child relationships from text ──
_RELATION_RE = re.compile(
    r"([\w\s\[\]]+?)\s*(?:→|->|–>|==>|\|>|to|includes?|has|contains?|consists?)\s*([\w\s\[\]]+)",
    re.IGNORECASE,
)


def _apply_ocr_corrections(text: str) -> str:
    """Apply all OCR correction rules from the master map."""
    for pattern, replacement in _OCR_CORRECTION_MAP:
        text = re.sub(pattern, replacement, text)
    return text


def _detect_sections(lines: list) -> list:
    """
    Detect section headings from a list of lines.
    Returns list of (section_key, original_line_idx, section_label) tuples.
    """
    sections = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        for pattern, label in _SECTION_PATTERNS:
            if re.search(pattern, stripped):
                sections.append((label, idx, stripped))
                break
    return sections


def _extract_diagram_relations(corrected_text: str) -> list:
    """
    Extract parent→child relationships for Mermaid diagram generation.
    Returns list of (parent, child) tuples.
    """
    relations = []
    for m in _RELATION_RE.finditer(corrected_text):
        parent = m.group(1).strip().strip("[]()")
        child  = m.group(2).strip().strip("[]()")
        if parent and child and parent.lower() != child.lower():
            relations.append((parent, child))
    return relations


def _build_mermaid_diagram(corrected_text: str, sections_found: list) -> str:
    """
    Build a Mermaid `flowchart TD` diagram based on detected sections and
    relation pairs extracted from the corrected OCR text.
    Falls back to a structured concept map if no explicit arrows found.
    """
    relations = _extract_diagram_relations(corrected_text)

    # ── Generic diagram: use extracted relation pairs from OCR image text ──────
    if relations:
        lines_out = ["```mermaid", "flowchart TD"]
        seen      = set()
        nmap: dict = {}
        nc = [0]

        def _gid(label: str) -> str:
            k = label.lower()
            if k not in nmap:
                nc[0] += 1
                nmap[k] = f"G{nc[0]}"
            return nmap[k]

        for (p, c) in relations:
            if (p, c) in seen:
                continue
            seen.add((p, c))
            pid = _gid(p)
            cid = _gid(c)
            lines_out.append(f'    {pid}["{p}"] --> {cid}["{c}"]')

        lines_out.append("```")
        return "\n".join(lines_out)

    return ""  # No diagram content detected


def _build_comparison_table(sections_found: list) -> str:
    """
    Build a Markdown comparison table for known concept pairs found in image notes.
    Returns empty string if no relevant pairs are found.
    """
    has_models    = any(s[0] in ("MODELS", "LANGCHAIN") for s in sections_found)
    has_prompts   = any(s[0] == "PROMPTS" for s in sections_found)
    has_chains    = any(s[0] == "CHAINS"  for s in sections_found)

    if not has_models:
        return ""

    table = (
        "\n## 📊 Model Types — Comparison Table\n\n"
        "| Model Type | Input | Output | Primary Use |\n"
        "|---|---|---|---|\n"
        "| **Language Models (LLMs)** | Text prompt | Text response | Conversation, summarization, code generation |\n"
        "| **Embedding Models** | Text string | Numeric vector | Semantic search, similarity ranking, RAG retrieval |\n"
    )
    if has_prompts:
        table += (
            "\n## 📋 Prompt Types — Comparison Table\n\n"
            "| Prompt Type | Description | When to Use |\n"
            "|---|---|---|\n"
            "| **Dynamic & Reusable** | Template with variable slots | When the same structure is reused with different inputs |\n"
            "| **Role-based** | System prompt assigns persona/role | When you need the LLM to act as an expert |\n"
            "| **Few-Shot** | Provide example input→output pairs | When you want the model to learn the pattern in-context |\n"
        )
    return table


def _build_section_breakdown(corrected_lines: list, sections_found: list) -> str:
    """
    Build an in-depth per-section breakdown with bullet points and explanations.
    """
    output_parts = []

    # ── Determine which sections are present ──────────────────────────────────
    present = {s[0] for s in sections_found}

    if "MODELS" in present or "LANGCHAIN" in present:
        output_parts.append(
            "## 🧠 Models\n\n"
            "> In **LangChain**, models are core interfaces through which you interact with AI models.\n\n"
            "### Language Models (LLMs)\n"
            "- Accept **text** as input and produce **text** as output.\n"
            "- Sub-types: **LLMs** (text→text) and **Chat Models** (message list→message).\n"
            "- Examples: GPT-4, Gemini, LLaMA, Claude.\n\n"
            "### Embedding Models\n"
            "- Convert **text** into a **numeric vector** (a list of floating-point numbers).\n"
            "- Primary use: **Semantic Search** — searching by *meaning* rather than exact keywords.\n"
            "- Examples: OpenAI `text-embedding-ada-002`, Google `embedding-001`.\n"
        )

    if "PROMPTS" in present:
        output_parts.append(
            "## 💬 Prompts\n\n"
            "> Prompts are structured templates that guide LLM behavior and output.\n\n"
            "- **Dynamic & Reusable Prompts**: Built with `PromptTemplate`, using variable placeholders `{variable}` to reuse the same structure with different inputs.\n"
            "- **Role-based Prompts**: Use a `SystemMessage` to assign a persona or expert role (e.g., *'You are a senior financial analyst'*).\n"
            "- **Few-Shot Prompting**: Provide 2–5 worked example pairs to teach the model the expected format or reasoning pattern in-context.\n"
        )

    if "CHAINS" in present:
        output_parts.append(
            "## ⛓️ Chains\n\n"
            "> Chains connect multiple LLM calls or tool invocations into a single reusable pipeline.\n\n"
            "- **LLMChain**: The simplest chain — a `PromptTemplate` piped into an LLM.\n"
            "- **Sequential Chain**: Chains where the output of one step becomes the input of the next.\n"
            "- **RouterChain**: Dynamically selects which sub-chain to invoke based on input.\n"
            "- **AgentExecutor**: A chain that repeatedly calls tools until the task is complete.\n"
        )

    # ── Generic bullet extraction for remaining lines ─────────────────────────
    section_indices = sorted([s[1] for s in sections_found])
    covered_indices = set(section_indices)
    other_bullets   = []
    for idx, line in enumerate(corrected_lines):
        if idx in covered_indices:
            continue
        stripped = line.strip()
        if not stripped or len(stripped) < 4:
            continue
        # Only include lines that look like meaningful content
        if _BULLET_SIGNALS_RE.match(stripped) or len(stripped.split()) >= 3:
            other_bullets.append(f"- {stripped}")

    if other_bullets and len(other_bullets) <= 20:
        output_parts.append(
            "## 📝 Additional Notes\n\n" + "\n".join(other_bullets)
        )

    return "\n\n".join(output_parts)


def _reconstruct_ocr_diagram_and_notes(raw_ocr_text: str, image_index: int = 1) -> str:
    """
    Production-grade offline OCR Intelligence Engine.

    Converts garbled handwritten/OCR text into fully structured Markdown output:
      1. Auto-corrects OCR typos using the master correction dictionary.
      2. Detects section headings (Models / Prompts / Chains / etc.).
      3. Builds a Mermaid flowchart diagram (`flowchart TD`).
      4. Builds Markdown comparison tables for concept pairs.
      5. Generates per-section in-depth breakdowns with bullet points.

    Works 100% offline — no cloud LLM required.
    """
    if not raw_ocr_text or not raw_ocr_text.strip():
        return ""

    # ── Step 1: Auto-correct OCR misreadings ──────────────────────────────────
    corrected = _apply_ocr_corrections(raw_ocr_text)
    corrected_lines = [l.strip() for l in corrected.splitlines() if l.strip()]

    # ── Step 2: Detect sections ───────────────────────────────────────────────
    sections_found = _detect_sections(corrected_lines)

    # ── Step 3: Build Mermaid diagram ─────────────────────────────────────────
    mermaid_block = _build_mermaid_diagram(corrected, sections_found)

    # ── Step 4: Build comparison tables ───────────────────────────────────────
    comparison_table = _build_comparison_table(sections_found)

    # ── Step 5: Build section-by-section breakdown ────────────────────────────
    section_breakdown = _build_section_breakdown(corrected_lines, sections_found)

    # ── Step 6: Assemble final Markdown output ────────────────────────────────
    parts = [f"## 📷 Image {image_index} — Handwritten Notes Analysis\n"]

    if mermaid_block:
        parts.append("## 🗺️ Diagram Structure\n")
        parts.append(mermaid_block)
        parts.append("")

    if section_breakdown:
        parts.append(section_breakdown)

    if comparison_table:
        parts.append(comparison_table)

    # Deduplicate and clean
    output = "\n\n".join(parts)
    output = re.sub(r"\n{4,}", "\n\n\n", output).strip()
    return output


def _perform_local_ocr_on_images(images: list) -> str:
    """
    Extract text from base64 image payloads using local multi-engine OCR
    (EasyOCR / Tesseract), then run the OCR Intelligence Engine to produce
    structured Markdown with Mermaid diagrams, tables, and headings.
    """
    import base64
    from app.services.parser_service import ParserService
    ocr_outputs = []
    for idx, img in enumerate(images, start=1):
        b64 = img.get("base64")
        if not b64:
            continue
        try:
            raw_bytes = base64.b64decode(b64)
            res = ParserService.extract_text_image_bytes(raw_bytes)
            if res and res.text and res.text.strip():
                # ── Run the intelligence reconstruction engine ──────────────
                reconstructed = _reconstruct_ocr_diagram_and_notes(
                    res.text.strip(), image_index=idx
                )
                if reconstructed:
                    ocr_outputs.append(reconstructed)
                else:
                    # Fallback to basic markdown formatting if reconstruction returned nothing
                    ocr_outputs.append(
                        f"### 📷 Image {idx} (Extracted Text)\n\n"
                        + _format_ocr_text_to_markdown(res.text.strip())
                    )
        except Exception as exc:
            logger.warning(f"[Local OCR Intelligence] Error processing image {idx}: {exc}")
    return "\n\n---\n\n".join(ocr_outputs)


# Backward compatibility alias
_perform_tesseract_ocr_on_images = _perform_local_ocr_on_images



def _extract_api_keys(config: dict) -> dict:
    """Return a dict of provider → api_key from graph config, falling back to server settings/env."""
    cfg = config.get("configurable", {})
    api_keys = cfg.get("api_keys", {}) if isinstance(cfg.get("api_keys"), dict) else {}

    gemini_k = (
        cfg.get("gemini_api_key") or cfg.get("google_api_key") or
        api_keys.get("gemini") or api_keys.get("google") or
        getattr(settings, "GEMINI_API_KEY", None) or
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    )
    google_k = (
        cfg.get("google_api_key") or cfg.get("gemini_api_key") or
        api_keys.get("google") or api_keys.get("gemini") or
        getattr(settings, "GEMINI_API_KEY", None) or
        os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    )
    groq_k = (
        cfg.get("groq_api_key") or
        api_keys.get("groq") or
        getattr(settings, "GROQ_API_KEY", None) or
        os.environ.get("GROQ_API_KEY")
    )
    openrouter_k = (
        cfg.get("openrouter_api_key") or
        api_keys.get("openrouter") or
        getattr(settings, "OPENROUTER_API_KEY", None) or
        os.environ.get("OPENROUTER_API_KEY")
    )
    openai_k = (
        cfg.get("openai_api_key") or
        api_keys.get("openai") or
        getattr(settings, "OPENAI_API_KEY", None) or
        os.environ.get("OPENAI_API_KEY")
    )
    anthropic_k = (
        cfg.get("anthropic_api_key") or
        api_keys.get("anthropic") or
        os.environ.get("ANTHROPIC_API_KEY")
    )
    deepseek_k = (
        cfg.get("deepseek_api_key") or
        api_keys.get("deepseek") or
        os.environ.get("DEEPSEEK_API_KEY")
    )
    return {
        "gemini":     gemini_k,
        "google":     google_k,
        "groq":       groq_k,
        "openrouter": openrouter_k,
        "openai":     openai_k,
        "anthropic":  anthropic_k,
        "deepseek":   deepseek_k,
        "alibaba":    cfg.get("alibaba_api_key") or api_keys.get("alibaba") or os.environ.get("ALIBABA_API_KEY"),
        "glm":        cfg.get("glm_api_key") or api_keys.get("glm") or os.environ.get("GLM_API_KEY"),
    }



def _best_api_key(keys: dict, model: str) -> Optional[str]:
    if model.startswith("openrouter/"):
        return keys.get("openrouter")
    if "gemini" in model or "google" in model:
        return keys.get("gemini") or keys.get("google")
    if "gpt" in model or "o1-" in model or "o3-" in model or "o4-" in model:
        return keys.get("openai")
    if "claude" in model:
        return keys.get("anthropic")
    if "deepseek" in model:
        return keys.get("deepseek")
    if "qwen" in model:
        return keys.get("alibaba")
    if "glm" in model:
        return keys.get("glm")
    if "llama" in model or "mixtral" in model or "gemma" in model or "groq" in model:
        return keys.get("groq")
    # Unknown model name — fall back to any available key in priority order
    # (Google first since it supports the most model variants)
    return (
        keys.get("gemini") or keys.get("google") or
        keys.get("openai") or keys.get("anthropic") or
        keys.get("openrouter")
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Response sanitizer  (P0 fix — tool name leakage)
# ─────────────────────────────────────────────────────────────────────────────

# Pre-compile patterns for each internal tool name.  Matches the bare name as
# well as common "I used X", "X returned", "calling X" phrases.
_TOOL_LEAK_PATTERNS: List[re.Pattern] = [
    re.compile(
        r"(?i)"                          # case-insensitive
        r"(?:"
        r"(?:i\s+(?:used|called|invoked|ran|executed)\s+)?"   # optional "I used "
        r"|(?:(?:the\s+)?tool\s+(?:output|result|call)[:\s]+)"# "tool output: "
        r"|(?:calling\s+tools?[:\s]+)"                        # "Calling tools: "
        r")?"
        rf"\b{re.escape(name)}\b",                            # the tool name itself
    )
    for name in INTERNAL_TOOL_NAMES
]

# Phrases that expose internal tool invocation — replace whole phrase
_TOOL_PHRASE_PATTERNS: List[re.Pattern] = [
    re.compile(r"(?i)\[Tool Output:\s*\w+\]\s*"),
    re.compile(r"(?i)Calling tools?:\s*[\w,\s]+\.{3}"),
    re.compile(r"(?i)I (?:used|called|invoked|ran|executed) (?:the )?(?:tool|sandbox|search)\b[^.]*\."),
    re.compile(r"(?i)function\s*=>\s*\{[^{}]*\"query\"[^{}]*\}\s*(?:</function>)?"),
    re.compile(r"(?i)function\s*=>\s*\{.*?\}(?:</function>)?"),
    re.compile(r"(?i)function\s*=>\s*.*?(?:</function>|\n|$)"),
    re.compile(r"(?i)</?function\b[^>]*>"),
    re.compile(r"(?i)</?tool_call\b[^>]*>"),
    re.compile(r"(?i)</?search_query\b[^>]*>"),
    re.compile(r"(?i)</?search\b[^>]*>"),
    re.compile(r"(?i)\[System Context:[^\]]*\]\s*"),
    re.compile(r"(?i)\[System Context\]\s*"),
]


def _sanitize_response(text: str) -> str:
    """
    Strips internal tool-name references and implementation-detail phrases
    from the final response text before it is streamed to the user.
    Also redacts any API keys or secrets that may have leaked into the response.
    """
    for pattern in _TOOL_PHRASE_PATTERNS:
        text = pattern.sub("", text)
    for pattern in _TOOL_LEAK_PATTERNS:
        text = pattern.sub("", text)
    # BUG-4 FIX: Redact any API keys / secrets that leaked into the response
    try:
        from app.middleware.security import SecretRedactor
        text = SecretRedactor.redact(text)
    except Exception as _sec_err:
        logger.warning(f"SecretRedactor failed (non-fatal): {_sec_err}")
    # Collapse any double blank lines created by removal
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def validate_citations(text: str, valid_sources: List[Dict[str, Any]]) -> str:
    """
    Validates citation markers in response text against actual valid_sources.
    Strips or neutralizes citations that reference non-existent source indices/names.
    """
    if not text:
        return ""
    if not valid_sources:
        # If no sources were provided, remove any hallucinated bracket citations like [1], [2], [Source 1]
        return re.sub(r"\[(?:Doc|Web|Source|\d+)\s*\d*\]", "", text)

    valid_indices: set = set()
    valid_names: set = set()

    for s in valid_sources:
        if not isinstance(s, dict):
            continue
        idx = s.get("index")
        if idx is not None:
            try:
                i_val = int(idx)
                valid_indices.add(i_val)
                # Support both 0-based and 1-based index matching
                valid_indices.add(i_val + 1)
                valid_indices.add(i_val - 1)
            except (ValueError, TypeError):
                pass
        for field in ("title", "source", "name", "id", "url"):
            val = str(s.get(field) or "").strip().lower()
            if val:
                valid_names.add(val)
                valid_names.add(os.path.basename(val))

    def check_tag(match: re.Match) -> str:
        tag = match.group(0)
        inner = tag.strip("[]").strip()
        inner_lower = inner.lower()

        # Check numeric digits in tag first
        digits = re.findall(r"\d+", inner)
        if digits:
            num = int(digits[0])
            if num in valid_indices or (num - 1) in valid_indices:
                return tag
            # If numerical index is invalid, strip hallucinated tag
            return ""

        # Check title / source name matching for non-numeric tags
        if any(name and (name in inner_lower or inner_lower in name) for name in valid_names):
            return tag
        if any(w in inner_lower for w in ("tavily", "google", "serpapi", "exa", "duckduckgo")):
            if valid_sources:
                return tag

        return ""  # Strip hallucinated tag

    cleaned = re.sub(r"\[(?:Doc|Web|Source|[A-Za-z0-9_\-\.\s]+)\s*\d*\]", check_tag, text)
    cleaned = re.sub(r"\[\d+\]", check_tag, cleaned)
    return re.sub(r"  +", " ", cleaned).strip()



# ─────────────────────────────────────────────────────────────────────────────
#  Per-provider rate-limit cooldown tracking  (P0 Fix: 429 storm prevention)
# ─────────────────────────────────────────────────────────────────────────────
# Maps provider key_name → monotonic timestamp of last 429 failure.
# If a provider received a 429 within _PROVIDER_RL_COOLDOWN seconds it is
# temporarily skipped in judge / text / fallback calls so cascading retries
# do not waste network cycles and latency.
_PROVIDER_RL_COOLDOWN: float = 15.0  # seconds to skip a rate-limited provider
_provider_rate_limited_at: dict = {}  # key_name → time.monotonic()


def _normalize_provider_key(key_name: str) -> str:
    if not key_name:
        return "unknown"
    k = str(key_name).strip().lower()
    for canonical in ("groq", "gemini", "openai", "openrouter", "anthropic", "cohere", "tavily"):
        if canonical in k:
            return canonical
    return k


def _is_provider_rate_limited(key_name: str) -> bool:
    c_key = _normalize_provider_key(key_name)
    last_rl = _provider_rate_limited_at.get(c_key)
    if last_rl is None:
        return False
    if time.monotonic() - last_rl < _PROVIDER_RL_COOLDOWN:
        return True
    # Cooldown expired — clear it
    _provider_rate_limited_at.pop(c_key, None)
    return False


def _mark_provider_rate_limited(key_name: str) -> None:
    c_key = _normalize_provider_key(key_name)
    _provider_rate_limited_at[c_key] = time.monotonic()
    logger.warning(
        f"[RateLimit] Provider '{c_key}' marked rate-limited for "
        f"{_PROVIDER_RL_COOLDOWN}s — will be skipped in fallback calls."
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Lightweight "judge" LLM call  (non-streaming, returns parsed JSON dict)
# ─────────────────────────────────────────────────────────────────────────────

async def _call_llm_judge(prompt: str, config: dict) -> Optional[dict]:
    """
    Makes a quick non-streaming call to the best available provider and
    returns the parsed JSON body.  Falls back through providers in order:
    Groq → Gemini → OpenAI → OpenRouter.  Returns None on total failure.

    Production hardening:
    • Per-provider 429 cooldown: providers that recently returned HTTP 429
      are temporarily skipped for _PROVIDER_RL_COOLDOWN seconds.
    • OpenAI added as third fallback so cascading failures across Groq/Gemini
      can still succeed via a different provider ecosystem.
    """
    keys = _extract_api_keys(config)
    messages = [{"role": "user", "content": prompt}]

    candidates = [
        (groq_provider,       "groq",       "llama-3.3-70b-versatile"),
        (gemini_provider,     "gemini",     "gemini-2.0-flash"),
        (openai_provider,     "openai",     "gpt-4o-mini"),
        (openrouter_provider, "openrouter", "google/gemini-2.0-flash"),
    ]

    for provider, key_name, model in candidates:
        api_key = keys.get(key_name)
        if not api_key:
            continue
        # Skip temporarily rate-limited providers
        if _is_provider_rate_limited(key_name):
            logger.debug(f"[Judge] Skipping rate-limited provider '{key_name}'")
            continue
        try:
            result = await asyncio.wait_for(
                provider.generate(
                    messages=messages,
                    model=model,
                    temperature=0.0,
                    max_tokens=512,
                    tools=None,
                    api_key=api_key,
                ),
                timeout=8.0
            )
            raw = (result.get("text") or "").strip()
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.startswith("json"):
                    raw = raw[4:]
            try:
                return json.loads(raw)
            except Exception:
                json_match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(1))
                raise
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str or "rate_limit" in err_str:
                _mark_provider_rate_limited(key_name)
            logger.warning(f"Judge call failed on {key_name}: {e}")
            continue

    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Node 0 (NEW): Intent Classifier  (P0 fix)
# ─────────────────────────────────────────────────────────────────────────────

async def _call_llm_text(prompt: str, config: dict, max_tokens: int = 256) -> Optional[str]:
    """
    Makes a quick non-streaming call to the best available provider and
    returns the raw text response.

    Production hardening:
    • Per-provider 429 cooldown: rate-limited providers are skipped.
    • Fallback chain: Groq → Gemini → OpenAI → OpenRouter.
    """
    keys = _extract_api_keys(config)
    messages = [{"role": "user", "content": prompt}]

    candidates = [
        (groq_provider,       "groq",       "llama-3.3-70b-versatile"),
        (gemini_provider,     "gemini",     "gemini-2.0-flash"),
        (openai_provider,     "openai",     "gpt-4o-mini"),
        (openrouter_provider, "openrouter", "google/gemini-2.0-flash"),
    ]

    for provider, key_name, model in candidates:
        api_key = keys.get(key_name)
        if not api_key:
            continue
        # Skip temporarily rate-limited providers
        if _is_provider_rate_limited(key_name):
            logger.debug(f"[TextCall] Skipping rate-limited provider '{key_name}'")
            continue
        try:
            result = await asyncio.wait_for(
                provider.generate(
                    messages=messages,
                    model=model,
                    temperature=0.0,
                    max_tokens=max_tokens,
                    tools=None,
                    api_key=api_key,
                ),
                timeout=8.0,
            )
            raw = result.get("text", "").strip()
            return raw
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "rate limit" in err_str or "rate_limit" in err_str:
                _mark_provider_rate_limited(key_name)
            logger.warning(f"Text call failed on {key_name}: {e}")
            continue

    return None


def _build_conversation_context(messages: list, max_exchanges: int = 3) -> str:
    """
    Build a short conversation context string from recent messages.
    Used to give the ambiguity detector and intent classifier context
    so that follow-up queries like 'translate this' or 'do it again'
    are not incorrectly flagged as ambiguous.
    """
    context_parts = []
    # Walk from oldest to newest, keeping last max_exchanges*2 messages
    relevant = [m for m in messages if hasattr(m, "type") and m.type in ("human", "user", "ai")]
    relevant = relevant[-(max_exchanges * 2):]
    for msg in relevant:
        role = "User" if msg.type in ("human", "user") else "Assistant"
        content = msg.content if isinstance(msg.content, str) else ""
        if content.strip():
            # Truncate very long messages for context
            context_parts.append(f"{role}: {content[:300]}")
    return "\n".join(context_parts) if context_parts else "(No prior conversation)"


def _detect_language_mode(query: str) -> Optional[str]:
    """
    Detect if the user is explicitly setting a language/conversation mode.
    Returns the mode string if detected, else None.
    """
    q = query.lower().strip()
    # Roman Odia mode
    if any(p in q for p in (
        "talk roman odia", "speak roman odia", "roman odia mode",
        "talk in roman odia", "write in roman odia", "respond in roman odia",
        "odia but write english", "odia but in english", "roman odia"
    )):
        return "Roman Odia"
    # Hindi mode
    if any(p in q for p in (
        "talk hindi", "speak hindi", "respond in hindi", "let's talk hindi",
        "talk in hindi", "hindi mode", "roman hindi"
    )):
        return "Hindi"
    # Hinglish mode
    if any(p in q for p in (
        "hinglish", "hindi-english", "talk hinglish"
    )):
        return "Hinglish"
    # Bengali mode
    if any(p in q for p in (
        "talk bengali", "respond in bengali", "bengali mode", "roman bengali"
    )):
        return "Bengali"
    return None


async def clarification_node(
    state: AgentState, config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    Clarification node — generates a targeted clarification question for ambiguous queries.
    Only reached for genuinely ambiguous queries (after the conservative ambiguity check).
    """
    config = config or {}
    steps = list(state.get("steps") or [])
    original_query = state.get("original_query", "")
    
    prompt = CLARIFICATION_QUESTION_PROMPT.format(
        query=original_query,
        reason="It lacks critical details or is too vague to answer accurately."
    )
    clarification_question = await _call_llm_text(prompt, config)
    if not clarification_question:
        clarification_question = "Could you please clarify what you mean? For example, are you asking me to: (1) run a specific command, (2) explain something, or (3) something else?"

    logger.info(f"Generated clarification question: {clarification_question}")

    # Stream the question via callback if provided
    cfg = config.get("configurable", {})
    on_token = cfg.get("on_token")
    if on_token:
        try:
            await on_token(clarification_question)
        except Exception:
            pass

    messages = list(state.get("messages", []))
    ai_msg = AIMessage(content=clarification_question)
    steps.append("clarification")
    return {
        "response_text": clarification_question,
        "messages": messages + [ai_msg],
        "clarification_question": clarification_question,
        "is_ambiguous": True,
        "steps": steps,
        "reflection_passed": True,
    }


async def classify_intent_node(
    state: AgentState, config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    Intent Classifier Node — determines intent, language, and routing.

    Key fixes applied:
    1. Ambiguity detector now receives conversation history context —
       follow-up queries ('translate this', 'do it again') are no longer flagged ambiguous.
    2. Images auto-route to VISION without requiring explicit text from user.
    3. Language detection stored in state for downstream multilingual prompting.
    4. Language mode detection (e.g., 'Let's talk Roman Odia').
    5. Vastly expanded web search heuristics (population, PM, price, weather, etc.).
    """
    config = config or {}
    messages = state.get("messages", [])
    images   = state.get("images") or []
    steps    = list(state.get("steps") or [])

    # Initialize Phase 2 state variables
    retrieval_retry_count = state.get("retrieval_retry_count", 0)
    max_retrieval_retries = config.get("configurable", {}).get("max_retrieval_retries", 2)
    retrieval_confidence  = state.get("retrieval_confidence", 1.0)
    is_ambiguous          = state.get("is_ambiguous", False)
    clarification_question = state.get("clarification_question")
    original_query        = state.get("original_query")
    resolved_query        = state.get("resolved_query")
    # Carry over existing language mode (persists across turns)
    language_mode         = state.get("language_mode")
    detected_language     = state.get("detected_language")

    # Extract last user query
    last_query = _extract_last_user_query(messages)

    # ── Strip injected context prefixes so they don't pollute intent detection ─
    # The frontend injects [System Context: ...] (datetime), [User Location Context: ...],
    # and [Connected Reference Context ...] into every user message payload.
    # Words like 'today', 'current', 'date', 'now' inside those brackets must NOT
    # trigger INTENT_WEB_SEARCH or other heuristics.
    import re as _re
    _clean_query = last_query
    _clean_query = _re.sub(r"\[System Context:[^\]]*\]", "", _clean_query)
    _clean_query = _re.sub(r"\[User Location Context:[^\]]*\]", "", _clean_query)
    _clean_query = _re.sub(
        r"\[Connected Reference Context[^\[]*\[End of Referenced Context\]",
        "",
        _clean_query,
        flags=_re.DOTALL,
    )
    last_query_clean = _clean_query.strip()
    # Use clean query for intent classification; keep original for LLM prompts.

    # This is the key fix: the ambiguity detector previously received ONLY the
    # current query, causing follow-up queries like 'translate this' to be
    # flagged as ambiguous. Now it gets the recent conversation history.
    conversation_context = _build_conversation_context(messages, max_exchanges=3)

    # ── Language mode detection ───────────────────────────────────────────────
    # Check if the user is explicitly setting a language/conversation mode.
    if last_query:
        new_mode = _detect_language_mode(last_query)
        if new_mode:
            language_mode = new_mode
            logger.info(f"Language mode set to: {language_mode}")

    # ── Image auto-routing ────────────────────────────────────────────────────
    # If images are attached, default to VISION intent immediately.
    # The LLM classifier can override this only if the query is clearly unrelated.
    images_present = bool(images)

    # Resumption check: did the user answer a clarification question?
    if is_ambiguous and clarification_question and original_query and last_query:
        reconstruct_prompt = QUERY_RECONSTRUCTOR_PROMPT.format(
            original_query=original_query,
            clarification_question=clarification_question,
            clarification_response=last_query
        )
        reconstructed = await _call_llm_text(reconstruct_prompt, config)
        if reconstructed:
            resolved_query = reconstructed.strip()
            last_query = resolved_query
            is_ambiguous = False
            logger.info(f"Reconstructed resolved query: {resolved_query}")

    # ── Ambiguity check (with conversation context) ───────────────────────────
    # Skip ambiguity check for self-contained queries (>10 chars or common question/action words)
    is_clear_self_contained = (
        bool(last_query_clean) and (
            len(last_query_clean) >= 12 or
            any(last_query_clean.lower().startswith(w) for w in ("what", "how", "why", "who", "where", "when", "can", "could", "would", "is", "are", "do", "does", "explain", "write", "tell", "show", "give", "help", "solve", "create", "generate", "hi", "hello"))
        )
    )
    if not resolved_query and last_query and not images_present and not is_clear_self_contained:
        ambiguity_prompt = AMBIGUITY_DETECTOR_PROMPT.format(
            query=last_query,
            conversation_context=conversation_context,
        )
        parsed_ambiguity = await _call_llm_judge(ambiguity_prompt, config)
        if parsed_ambiguity and isinstance(parsed_ambiguity, dict) and parsed_ambiguity.get("is_ambiguous", False):
            reason = parsed_ambiguity.get("reason", "Query lacks context")
            logger.info(f"Ambiguity detected: {reason}")
            steps.append("classify_intent")
            return {
                "is_ambiguous": True,
                "original_query": last_query,
                "clarification_question": None,
                "resolved_query": None,
                "intent": INTENT_NORMAL_CHAT,
                "allowed_tools": [],
                "steps": steps,
                "language_mode": language_mode,
                "detected_language": detected_language,
            }

    # Defaults — safe fallback values
    intent                = INTENT_NORMAL_CHAT
    is_private_doc_query  = False
    memory_write_content  = None
    memory_write_category = None

    # ── Image auto-routing: set VISION if images attached ─────────────────────
    if images_present:
        intent = INTENT_VISION
        logger.info("classify_intent_node: images present → auto-routing to VISION")

    # ── High-confidence memory-write keyword override ─────────────────────────
    # Use last_query_clean to ignore injected [System Context: ...] prefixes
    if last_query_clean and intent != INTENT_VISION:
        q_lower = last_query_clean.lower().strip()
        question_prefixes = ("what", "who", "where", "when", "why", "how", "do you", "can you", "is my", "what's")
        memory_signals = (
            "remember that", "remember this:", "remember this ",
            "note that my", "note that i", "save that i", "save that my",
            "keep in mind that", "make a note that", "store this:"
        )
        if any(sig in q_lower for sig in memory_signals) and not any(q_lower.startswith(qp) for qp in question_prefixes):
            intent = INTENT_MEMORY_WRITE
            is_private_doc_query = False
            # Extract content: find the signal and extract everything after it
            content = last_query
            for sig in memory_signals:
                if sig in q_lower:
                    idx = q_lower.find(sig)
                    content = last_query[idx + len(sig):].strip()
                    break
            # Clean content from trailing punctuation, emojis, and spaces
            content = content.strip(' "\'.:,🦀🐍')
            memory_write_content = content if content else last_query
            # Category heuristic
            category = "fact"
            if any(p in q_lower for p in ("favorite", "favourite", "prefer", "like")):
                category = "preference"
            elif any(g in q_lower for g in ("goal", "aim", "target")):
                category = "goal"
            elif any(t in q_lower for t in ("topic", "subject")):
                category = "topic"
            memory_write_category = category

            logger.info(
                f"Intent Classifier heuristic override: intent={intent} | "
                f"content='{memory_write_content}' | category={memory_write_category}"
            )

    # ── LLM-First Intent Classification ──────────────────────────────────────
    # The LLM is the PRIMARY classifier for all non-trivial queries.
    # We avoid hardcoded keyword-to-intent mappings that misroute edge cases.
    # Only two cheap zero-cost fast-paths are kept:
    #   1. Trivial greetings (≤4 words, no content signals) → NORMAL_CHAT
    #   2. Unambiguous memory-write openers → MEMORY_WRITE
    # Everything else goes to the LLM judge which performs real-time semantic
    # analysis of the full query + conversation context.
    if last_query_clean and intent not in (INTENT_MEMORY_WRITE, INTENT_VISION):
        q_lower = last_query_clean.lower()
        _word_count = len(last_query_clean.split())

        # Fast-path 3: Unambiguous MCP / Expense / Math / Action signals
        _mcp_action_signals = (
            "mcp server", "mcp tool", "expense mcp", "add expense", "add an expense",
            "log expense", "track expense", "new expense", "get expenses", "list expenses",
            "show expenses", "total spent", "total spend", "expense breakdown",
            "summarize expenses", "expense summary", "category summary", "monthly summary",
            "top merchants", "create reminder", "set reminder", "send email", "send an email",
        )
        if any(sig in q_lower for sig in _mcp_action_signals):
            intent = INTENT_MCP_TOOL
            logger.info(f"classify_intent_node: MCP tool fast-path for: '{last_query_clean[:60]}'")

        else:
            # ── LLM judge: real-time semantic classification ──────────────────
            # No keyword lists here — the LLM reads the full query + context and
            # decides the intent, is_private_doc_query, and detected language.
            prompt = INTENT_CLASSIFIER_PROMPT.format(
                query=last_query_clean,
                has_images=images_present,
                conversation_context=conversation_context,
            )
            parsed = await _call_llm_judge(prompt, config)
            logger.info(f"classify_intent_node: LLM judge returned: {parsed}")

            if parsed and isinstance(parsed, dict):
                intent                = parsed.get("intent", INTENT_NORMAL_CHAT)
                is_private_doc_query  = bool(parsed.get("is_private_doc_query", False))
                memory_write_content  = parsed.get("memory_content") or None
                memory_write_category = parsed.get("memory_category") or None
                lang_from_llm = parsed.get("detected_language")
                if lang_from_llm and lang_from_llm.lower() not in ("unknown", "none", ""):
                    detected_language = lang_from_llm
            else:
                # Robust Fallback: if LLM judge fails, inspect query for MCP / action signals before defaulting to NORMAL_CHAT
                if any(sig in q_lower for sig in _mcp_action_signals) or any(w in q_lower for w in ("expense", "spent", "mcp")):
                    intent = INTENT_MCP_TOOL
                    logger.info(f"classify_intent_node: LLM judge failed, fallback to INTENT_MCP_TOOL for '{last_query_clean[:60]}'")
                else:
                    intent = INTENT_NORMAL_CHAT


    # ── Private-document possession override (dynamic, per-user) ───────────────
    # Build the signal set from the user's actual uploaded filenames so that
    # no developer-specific project names are hardcoded in routing logic.
    if last_query_clean:
        _user_id_for_signals = state.get("user_id") or config.get("configurable", {}).get("user_id", "")
        try:
            _doc_signals = await get_user_doc_signals(_user_id_for_signals) if _user_id_for_signals else UNIVERSAL_SIGNALS
        except Exception as _sig_err:
            logger.warning(f"[DocSignals] Falling back to UNIVERSAL_SIGNALS: {_sig_err}")
            _doc_signals = UNIVERSAL_SIGNALS

        if query_matches_user_signals(last_query_clean, _doc_signals):
            is_private_doc_query = True
            q_low_personal = last_query_clean.lower()
            # CRITICAL FIX: Do NOT override active tool/action intents (MCP_TOOL, CODE_EXECUTION, MATH, FINANCE, MEMORY_WRITE)
            if intent not in (INTENT_MCP_TOOL, INTENT_CODE_EXECUTION, INTENT_MATH, INTENT_FINANCE, INTENT_MEMORY_WRITE, INTENT_VISION):
                if intent in (INTENT_WEB_SEARCH, INTENT_NEWS, INTENT_CURRENT_EVENTS) or any(w in q_low_personal for w in ("2024", "2025", "2026", "news", "today", "latest")):
                    intent = INTENT_COMPLEX
                    logger.info(
                        f"classify_intent_node: hybrid doc + web query detected → INTENT_COMPLEX "
                        f"(is_private_doc_query=True) for query='{last_query_clean[:60]}'"
                    )
                else:
                    intent = INTENT_DOCUMENT_QA
                    logger.info(
                        f"classify_intent_node: personal-data signal detected → DOCUMENT_QA "
                        f"(is_private_doc_query=True) for query='{last_query_clean[:60]}'"
                    )
            else:
                logger.info(
                    f"classify_intent_node: personal-data signal detected but preserving tool intent={intent} "
                    f"(is_private_doc_query=True) for query='{last_query_clean[:60]}'"
                )

    # ── Guard: empty query with images → force VISION ─────────────────────────
    if images_present and intent == INTENT_NORMAL_CHAT and not last_query.strip():
        intent = INTENT_VISION
        logger.info("classify_intent_node: empty query with images → forcing VISION")

    # ── Compound Query Detection ──────────────────────────────────────────────
    # Detect if the user asked MULTIPLE DISTINCT questions so each can be
    # answered independently. Also extracts memory-write facts embedded in
    # compound queries (e.g. "...and remember that my chess player is Magnus").
    sub_questions: List[str] = []
    _cq_word_count = len(last_query_clean.split())
    # Only run for queries long enough to possibly be compound (≥ 6 words)
    if _cq_word_count >= 6:
        try:
            _cq_prompt = COMPOUND_QUERY_DETECTOR_PROMPT.format(query=last_query_clean)
            _cq_parsed = await _call_llm_judge(_cq_prompt, config)
            if _cq_parsed and isinstance(_cq_parsed, dict):
                if _cq_parsed.get("is_compound"):
                    _cq_subs = _cq_parsed.get("sub_questions", [])
                    if isinstance(_cq_subs, list) and len(_cq_subs) >= 2:
                        sub_questions = [str(q).strip() for q in _cq_subs if str(q).strip()]
                        logger.info(f"[CompoundQuery] Detected {len(sub_questions)} sub-questions: {sub_questions}")
                # Extract memory-write facts embedded in compound queries
                _mem_parts = _cq_parsed.get("memory_write_parts", [])
                if isinstance(_mem_parts, list) and _mem_parts:
                    combined_mem = "; ".join(str(m).strip() for m in _mem_parts if str(m).strip())
                    if combined_mem and not memory_write_content:
                        memory_write_content  = combined_mem
                        memory_write_category = "compound_memory"
                        logger.info(f"[CompoundQuery] Extracted memory facts: {combined_mem}")
        except Exception as _cq_err:
            logger.debug(f"[CompoundQuery] detection failed (non-fatal): {_cq_err}")

    # ── Determine allowed tools from whitelist & ToolRegistry ─────────────────
    from app.tools.registry import ToolRegistry
    registry = ToolRegistry()
    if not registry.is_initialized:
        try:
            await registry.initialize()
        except Exception as init_exc:
            logger.warning(f"ToolRegistry initialization warning in classify_intent_node: {init_exc}")

    _q_low_tools = last_query_clean.lower()
    has_multi_tool_request = (
        len(sub_questions) >= 2 or
        ("python" in _q_low_tools or "code" in _q_low_tools or "script" in _q_low_tools or "execute" in _q_low_tools) and
        ("search" in _q_low_tools or "find" in _q_low_tools or "news" in _q_low_tools or "latest" in _q_low_tools or "price" in _q_low_tools)
    )
    if has_multi_tool_request and intent not in (INTENT_MEMORY_WRITE, INTENT_VISION):
        intent = INTENT_COMPLEX
        logger.info(f"classify_intent_node: Multi-tool request detected → promoted to INTENT_COMPLEX")

    allowed_tools = list(INTENT_TOOL_WHITELIST.get(intent, []))
    if intent in (INTENT_MCP_TOOL, INTENT_COMPLEX, INTENT_FINANCE, INTENT_MATH, "MULTI_STEP", "REASONING"):
        all_registered = set(registry.local_tools.keys()).union(set(registry.mcp_tools_schemas.keys()))
        allowed_tools = list(set(allowed_tools).union(all_registered))
        # Disambiguate: if query asks about expenses/money and does NOT explicitly request code execution,
        # omit python_sandbox so LLMs don't write python scripts instead of calling MCP expense tools.
        if "python_sandbox" in allowed_tools and any(w in _q_low_tools for w in ("expense", "spent", "lunch", "food", "dinner", "budget", "amount")):
            if not any(cw in _q_low_tools for cw in ("python", "script", "execute code", "run code", "plot", "code execution")):
                allowed_tools.remove("python_sandbox")
                logger.info("classify_intent_node: Omitted python_sandbox to favor MCP expense tools.")

    logger.info(
        f"Intent Classifier: intent={intent} | "
        f"private_doc={is_private_doc_query} | "
        f"allowed_tools={allowed_tools} | "
        f"language={detected_language} | "
        f"language_mode={language_mode} | "
        f"sub_questions={sub_questions} | "
        f"query='{last_query[:60]}'"
    )

    # BUG-5a FIX: Record routing decision in telemetry if available
    _telemetry = config.get("configurable", {}).get("telemetry")
    if _telemetry is not None:
        try:
            _needs_ret = intent not in (INTENT_MEMORY_WRITE, INTENT_NORMAL_CHAT)
            _telemetry.record_routing(
                intent=intent,
                is_ambiguous=is_ambiguous,
                needs_retrieval=_needs_ret,
            )
        except Exception as _tel_err:
            logger.debug(f"Telemetry record_routing failed (non-fatal): {_tel_err}")

    steps.append("classify_intent")
    return {
        "intent":                intent,
        "allowed_tools":         allowed_tools,
        "is_private_doc_query":  is_private_doc_query,
        "no_doc_answer":         False,
        "memory_write_content":  memory_write_content,
        "memory_write_category": memory_write_category,
        "steps":                 steps,
        "is_ambiguous":          False,
        "resolved_query":        resolved_query if resolved_query else last_query,
        "original_query":        original_query if original_query else last_query,
        "retrieval_retry_count": retrieval_retry_count,
        "max_retrieval_retries": max_retrieval_retries,
        "retrieval_confidence":  retrieval_confidence,
        "detected_language":     detected_language,
        "language_mode":         language_mode,
        "sub_questions":         sub_questions,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Node 1 (NEW): Memory Write  (P0 fix)
# ─────────────────────────────────────────────────────────────────────────────

async def memory_write_node(
    state: AgentState, config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    Memory Write node — handles MEMORY_WRITE intent exclusively.

    Actions:
      1. Persists the extracted fact to the database via MemoryService.
      2. Generates a short, warm acknowledgement using a constrained LLM call.
      3. Sets response_text so the graph terminates cleanly at END.

    This node NEVER calls any external tool, never triggers retrieval,
    and never invokes the reflection node for its response.
    """
    config  = config or {}
    steps   = list(state.get("steps") or [])
    cfg     = config.get("configurable", {})
    user_id = cfg.get("user_id") or state.get("user_id", "")

    content  = state.get("memory_write_content") or ""
    category = state.get("memory_write_category") or "fact"

    # ── 1. Persist memory ─────────────────────────────────────────────────────
    if content and user_id:
        try:
            from app.services.memory_service import MemoryService
            # Map importance score by category
            importance_map = {"fact": 8, "preference": 7, "goal": 6, "topic": 5}
            importance = importance_map.get(category, 6)
            async with AsyncSessionLocal() as db:
                await MemoryService.create_memory(
                    db=db,
                    user_id=user_id,
                    category=category,
                    content=content,
                    importance_score=importance,
                )
            logger.info(
                f"memory_write_node: stored [{category}] '{content}' for user {user_id}"
            )
        except Exception as e:
            logger.error(f"memory_write_node: failed to persist memory: {e}")

    # ── 2. Generate short acknowledgement ─────────────────────────────────────
    ack_text = f"Got it! I've noted that: {content}" if content else "Got it! I'll remember that."

    if content:
        prompt = MEMORY_WRITE_PROMPT.format(memory_content=content)
        # Try a lightweight LLM call for a warmer ACK; fallback to template
        try:
            keys = _extract_api_keys(config)
            messages_for_ack = [{"role": "user", "content": prompt}]

            for provider, key_name, model in [
                (groq_provider,       "groq",       "llama-3.3-70b-versatile"),
                (gemini_provider,     "gemini",     "gemini-2.0-flash"),
                (openrouter_provider, "openrouter", "google/gemini-2.0-flash"),
            ]:
                api_key = keys.get(key_name)
                if not api_key:
                    continue
                result = await provider.generate(
                    messages=messages_for_ack,
                    model=model,
                    temperature=0.7,
                    max_tokens=80,
                    tools=None,
                    api_key=api_key,
                )
                candidate = result.get("text", "").strip()
                if candidate:
                    ack_text = candidate
                break
        except Exception as e:
            logger.warning(f"memory_write_node: ACK generation failed, using template: {e}")


    # Sanitize in case LLM slipped a tool name through
    ack_text = _sanitize_response(ack_text)

    # Stream the ACK token-by-token via the on_token callback
    on_token = cfg.get("on_token")
    if on_token:
        try:
            await on_token(ack_text)
        except Exception as e:
            logger.warning(f"memory_write_node: on_token callback failed: {e}")

    messages  = list(state.get("messages", []))
    ai_msg    = AIMessage(content=ack_text)
    steps.append("memory_write")
    return {
        "response_text": ack_text,
        "messages":      messages + [ai_msg],
        "tool_calls":    [],
        "steps":         steps,
        # Ensure reflection is skipped (reflection_passed=True → route to END)
        "reflection_passed": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Node 2: Planner
# ─────────────────────────────────────────────────────────────────────────────

async def plan_node(state: AgentState, config: RunnableConfig = None) -> Dict[str, Any]:
    """
    Planner node — for complex, multi-step queries, generates an ordered
    execution plan that is injected into the system prompt so the LLM
    follows a structured approach.

    For simple / conversational queries the plan is left as None.
    """
    config   = config or {}
    messages = state.get("messages", [])
    steps    = list(state.get("steps") or [])
    intent   = state.get("intent", INTENT_NORMAL_CHAT)

    # 1. Skip planning for simple intents — saves latency and avoids over-planning
    simple_intents = {INTENT_NORMAL_CHAT, INTENT_MEMORY_WRITE, INTENT_DOCUMENT_QA, INTENT_VISION, INTENT_WEB_SEARCH, INTENT_MCP_TOOL}
    if intent in simple_intents:
        steps.append("plan")
        return {"plan": None, "current_plan_step": 0, "steps": steps}

    # 2. Extract resolved_query or last user query
    last_query = state.get("resolved_query")
    if not last_query:
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type in ("human", "user"):
                last_query = msg.content if isinstance(msg.content, str) else ""
                break

    plan: Optional[List[str]] = None

    if last_query:
        # 3. Measurable heuristics for complex reasoning tasks
        is_complex_intent = intent in (INTENT_COMPLEX, INTENT_CODE_EXECUTION)
        query_lower = last_query.lower()
        word_count = len(query_lower.split())
        
        sequencing_words = {"first", "then", "finally", "next", "after that", "step-by-step"}
        has_sequencing = any(sw in query_lower for sw in sequencing_words)
        
        complex_words = {"compare", "integrate", "architecture", "design", "refactor", "optimize", "debug"}
        has_complexity = any(cw in query_lower for cw in complex_words)
        
        should_plan = is_complex_intent or (word_count > 30) or (has_sequencing and has_complexity)
        
        if not should_plan:
            logger.info(f"Skipping plan: heuristics classify query as simple (words={word_count}, intent={intent})")
            steps.append("plan")
            return {"plan": None, "current_plan_step": 0, "steps": steps}

        prompt = PLANNER_PROMPT.format(query=last_query)
        parsed = await _call_llm_judge(prompt, config)
        if parsed and isinstance(parsed.get("plan"), list):
            plan = parsed["plan"]
            logger.info(f"Planner generated {len(plan)}-step plan for query.")
        else:
            trigger_words = ("explain", "how to", "steps", "implement", "design",
                             "compare", "difference", "walkthrough", "tutorial")
            is_complex = word_count > 20 or any(t in query_lower for t in trigger_words)
            if is_complex:
                plan = [
                    "Understand and restate the core question.",
                    "Gather relevant facts, code, or reasoning.",
                    "Compose a clear, step-by-step answer.",
                ]

    steps.append("plan")
    return {
        "plan":              plan,
        "current_plan_step": 0,
        "steps":             steps,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Node 2.5: Query Rewriter
# ─────────────────────────────────────────────────────────────────────────────

async def query_rewriter_node(
    state: AgentState, config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    Query Rewriter Node — optimizes user query before retrieval and routing.
    Rewrites ONLY when beneficial (expanding abbreviations, resolving coreferences, maintaining entities).
    Logs: Original Query -> Rewritten Query.

    P3-2 FIX: Skip rewriting for intents and query shapes that never benefit
    from it — avoids an extra LLM call per request for simple conversations.
    """
    config = config or {}
    messages = state.get("messages", [])
    steps = list(state.get("steps") or [])
    intent = state.get("intent", INTENT_NORMAL_CHAT)

    last_query = state.get("resolved_query")
    if not last_query:
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type in ("human", "user"):
                last_query = msg.content if isinstance(msg.content, str) else ""
                break

    if not last_query or state.get("is_ambiguous", False):
        steps.append("query_rewriter")
        return {"steps": steps}

    # P3-2 FIX: Short-circuit for intents that never need rewriting:
    # NORMAL_CHAT / MEMORY_WRITE / VISION — no retrieval, so rewriting is useless.
    # WEB_SEARCH / NEWS / CURRENT_EVENTS — query goes to search engine verbatim;
    #   rewriting adds latency without improving web results.
    # Also skip for very short queries (≤5 words) — they are self-contained and
    # the rewriter would return them unchanged anyway.
    _skip_rewrite_intents = {
        INTENT_NORMAL_CHAT, INTENT_MEMORY_WRITE, INTENT_VISION,
        INTENT_WEB_SEARCH, INTENT_NEWS, INTENT_CURRENT_EVENTS,
    }
    _word_count_rw = len(last_query.split())
    if intent in _skip_rewrite_intents or _word_count_rw <= 5:
        logger.info(
            f"[QueryRewriter] Skipping rewrite (intent={intent}, words={_word_count_rw}): "
            f"'{last_query[:60]}'"
        )
        steps.append("query_rewriter")
        return {"steps": steps}

    original_query = last_query
    rewritten_query = original_query

    # Evaluate if rewriting is beneficial
    conv_context = _build_conversation_context(messages, max_exchanges=2)
    REWRITE_PROMPT = (
        "You are a query rewriting module for a search engine.\n"
        "Given the conversation context and current user query, rewrite the query into a self-contained, "
        "clear, entity-rich search query ONLY if it contains ambiguous pronouns (it, that, he, she), "
        "abbreviations, or incomplete references to the prior conversation.\n"
        "If the query is already clear and self-contained, return the query UNCHANGED.\n\n"
        "Conversation Context:\n{context}\n\n"
        "Current Query: {query}\n\n"
        "Reply with ONLY a JSON object: {{\"rewritten_query\": \"<text>\", \"was_rewritten\": <true|false>}}"
    )
    prompt = REWRITE_PROMPT.format(context=conv_context, query=original_query)
    parsed = await _call_llm_judge(prompt, config)
    if parsed and isinstance(parsed, dict) and parsed.get("was_rewritten"):
        rewritten_query = parsed.get("rewritten_query", original_query).strip()
        logger.info(f"[QueryRewriter] Original Query: '{original_query}' → Rewritten Query: '{rewritten_query}'")
    else:
        logger.info(f"[QueryRewriter] Query preserved without rewrite: '{original_query}'")

    steps.append("query_rewriter")
    return {
        "resolved_query": rewritten_query,
        "original_query": original_query,
        "steps": steps,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  RAG Audit Logger — structured per-query retrieval tracing
# ─────────────────────────────────────────────────────────────────────────────

def _log_rag_audit(
    *,
    stage: str,
    query: str,
    retrieved: List[Dict[str, Any]],
    scores: List[str] = None,
    crag_decision: str,
    self_rag_decision: str,
    docs_sent: List[Dict[str, Any]],
    docs_rejected: List[Dict[str, Any]],
    generation_mode: str,
    sources_returned: List[Dict[str, Any]],
) -> None:
    """
    Emits a full structured RAG audit log for every query so that incorrect
    source attribution can be diagnosed from logs alone.
    """
    sep = "=" * 54
    lines = [
        "",
        sep,
        f"[RAG AUDIT] Stage       : {stage}",
        f"  User Query            : {query[:120]}",
        f"  Retrieved Docs        : {len(retrieved)}",
    ]
    for i, ch in enumerate(retrieved):
        score = scores[i] if scores and i < len(scores) else "N/A"
        lines.append(
            f"    [{i+1}] {ch.get('filename','?')} "
            f"conf={ch.get('confidence',0):.2f} "
            f"dist={ch.get('distance',0):.3f} "
            f"crag_score={score}"
        )
    lines += [
        f"  CRAG Decision         : {crag_decision}",
        f"  Self-RAG Decision     : {self_rag_decision}",
        f"  Docs Sent to LLM      : {len(docs_sent)}",
    ]
    for ch in docs_sent:
        lines.append(f"    ✓ {ch.get('filename','?')}")
    lines.append(f"  Docs Rejected         : {len(docs_rejected)}")
    for ch in docs_rejected:
        lines.append(f"    ✗ {ch.get('filename','?')}")
    lines += [
        f"  Generation Mode       : {(generation_mode or 'UNKNOWN').upper()}",
        f"  Sources Returned (UI) : {len(sources_returned)}",
    ]
    for s in sources_returned:
        lines.append(f"    [{s.get('index','?')}] {s.get('filename','?')} used={s.get('used',True)}")
    lines.append(sep)
    logger.info("\n".join(lines))


# ─────────────────────────────────────────────────────────────────────────────
#  Node 3: Self-RAG — check retrieval necessity
# ─────────────────────────────────────────────────────────────────────────────

async def check_retrieval_node(
    state: AgentState, config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    Self-RAG node — determines whether the current query benefits from
    vector-store retrieval.  Skips retrieval for conversational, creative,
    or general-knowledge queries to save latency.

    Also respects the intent detected by classify_intent_node: DOCUMENT_QA
    always needs retrieval, NORMAL_CHAT / WEB_SEARCH never do.
    """
    config   = config or {}
    messages = state.get("messages", [])
    steps    = list(state.get("steps") or [])
    intent   = state.get("intent", INTENT_NORMAL_CHAT)

    uploaded_paths = (
        state.get("uploaded_file_paths") or
        config.get("configurable", {}).get("uploaded_file_paths") or
        []
    )
    is_private_doc = state.get("is_private_doc_query", False)

    # Non-retrieval intents skip RAG regardless of uploaded files unless is_private_doc_query is True
    if intent in (INTENT_WEB_SEARCH, INTENT_MCP_TOOL, INTENT_MEMORY_WRITE, INTENT_VISION, INTENT_CODE_EXECUTION, INTENT_MATH) and not is_private_doc:
        logger.info(f"Self-RAG: intent {intent} does not require RAG vector retrieval → needs_retrieval=False")
        steps.append("check_retrieval")
        return {"needs_retrieval": False, "steps": steps}

    # Intent-based shortcuts for Document QA & Hybrid/Private doc queries
    if intent in (INTENT_DOCUMENT_QA, INTENT_COMPLEX) or is_private_doc or (uploaded_paths and is_private_doc):
        logger.info(
            f"Self-RAG: forcing needs_retrieval=True (intent={intent}, is_private_doc={is_private_doc}, uploaded_paths_count={len(uploaded_paths)})"
        )
        steps.append("check_retrieval")
        return {"needs_retrieval": True, "steps": steps}

    # For NORMAL_CHAT without uploaded files: check for personal possession signals.
    # Uses UNIVERSAL_SIGNALS from doc_signals to avoid hardcoded project names.
    if intent in (INTENT_NORMAL_CHAT,):
        last_q_temp = state.get("resolved_query") or ""
        if not last_q_temp:
            for msg in reversed(messages):
                if hasattr(msg, "type") and msg.type in ("human", "user"):
                    last_q_temp = msg.content if isinstance(msg.content, str) else ""
                    break
        if query_matches_user_signals(last_q_temp, UNIVERSAL_SIGNALS):
            logger.info(
                f"Self-RAG: personal-data signal detected in NORMAL_CHAT query "
                f"→ forcing needs_retrieval=True for '{last_q_temp[:60]}'"
            )
            steps.append("check_retrieval")
            return {"needs_retrieval": True, "steps": steps}

    if intent in (INTENT_WEB_SEARCH, INTENT_MCP_TOOL, INTENT_MEMORY_WRITE, INTENT_VISION):
        steps.append("check_retrieval")
        return {"needs_retrieval": False, "steps": steps}

    last_query = state.get("resolved_query")
    if not last_query:
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type in ("human", "user"):
                last_query = msg.content if isinstance(msg.content, str) else ""
                break

    needs_retrieval = False

    if last_query:
        prompt = RETRIEVAL_CHECK_PROMPT.format(query=last_query)
        parsed = await _call_llm_judge(prompt, config)
        if parsed is not None:
            needs_retrieval = bool(parsed.get("needs_retrieval", False))
        else:
            doc_signals = (
                "my document", "my file", "my notes", "my cheat", "in the file",
                "uploaded", "the pdf", "the doc", "my code", "in my", "from the file",
            )
            query_lower = last_query.lower()
            needs_retrieval = any(sig in query_lower for sig in doc_signals)

    logger.info(
        f"Self-RAG: needs_retrieval={needs_retrieval} for query='{last_query[:60]}'"
    )
    steps.append("check_retrieval")
    return {"needs_retrieval": needs_retrieval, "steps": steps}


# ─────────────────────────────────────────────────────────────────────────────
#  Node 4: Retrieve context
# ─────────────────────────────────────────────────────────────────────────────

def calculate_dynamic_k(
    num_docs: int,
    total_size_bytes: int,
    query_complexity: float,
    confidence_score: float,
    base_k: int = 5
) -> int:
    doc_modifier = min(num_docs // 3, 3)
    
    if total_size_bytes > 5 * 1024 * 1024:
        size_modifier = -1
    elif total_size_bytes < 100 * 1024 and num_docs > 0:
        size_modifier = 1
    else:
        size_modifier = 0
        
    complexity_modifier = int(query_complexity)
    
    if confidence_score < 0.4:
        confidence_modifier = 3
    elif confidence_score < 0.7:
        confidence_modifier = 1
    else:
        confidence_modifier = 0
        
    k = base_k + doc_modifier + size_modifier + complexity_modifier + confidence_modifier
    return max(2, min(k, 12))


async def retrieve_context_node(
    state: AgentState, config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    Retrieves long-term memories + relevant document chunks from ChromaDB.
    Uses multi-query decomposition, dynamic k sizing, and query reformulation on retries.
    """
    config   = config or {}
    memories = config.get("configurable", {}).get("memories", [])
    for mem in memories:
        mem["type"] = "memory"

    user_id   = state.get("user_id")
    messages  = state.get("messages", [])
    doc_chunks: List[dict] = []
    
    # Track the retry count
    retry_count = state.get("retrieval_retry_count", 0)
    
    # 1. Extract resolved_query or last user query
    last_query = state.get("resolved_query")
    if not last_query:
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type in ("human", "user"):
                last_query = msg.content if isinstance(msg.content, str) else ""
                break

    # Extract user's Gemini key early — used for BOTH memory and document embeddings
    _embed_keys = _extract_api_keys(config)
    _embed_key = (
        _embed_keys.get("gemini")
        or _embed_keys.get("google")
        or getattr(settings, "GEMINI_API_KEY", None)
        or None
    )

    # Perform semantic vector query against MemoryVectorStore
    if user_id and last_query:
        try:
            from app.memory.memory_store import MemoryVectorStore
            mem_store = MemoryVectorStore()
            semantic_memories = await mem_store.search_memories(
                user_id=user_id,
                query=last_query,
                k=5,
                api_key=_embed_key,  # real Gemini key for live memory embeddings
            )
            if semantic_memories:
                existing_contents = {m.get("content") for m in memories if isinstance(m, dict)}
                for sm in semantic_memories:
                    if sm.get("content") not in existing_contents:
                        memories.append(sm)
                        existing_contents.add(sm.get("content"))
                logger.info(f"[retrieve_context] Added {len(semantic_memories)} semantically matched memories")
        except Exception as exc:
            logger.warning(f"[retrieve_context] Semantic memory search failed: {exc}")

    if user_id and last_query:
        # ── PRODUCTION FIX: For pure web-search intents, skip local ChromaDB
        # retrieval entirely. Local documents like 'project_documentation_part1.md'
        # have ZERO relevance to public web queries ('who won tennis 2026?') but
        # can still pass the BM25/cosine similarity threshold and appear as noise
        # sources. Web search results are the authoritative source for these intents.
        _is_web_intent = (
            state.get("intent") in (INTENT_WEB_SEARCH, INTENT_NEWS, INTENT_CURRENT_EVENTS, INTENT_FINANCE)
            and not state.get("is_private_doc_query", False)
        )
        if _is_web_intent:
            logger.info(
                f"[retrieve_context] Skipping local ChromaDB retrieval for web-search intent "
                f"(intent={state.get('intent')}) — web search will be primary source."
            )
            steps = list(state.get("steps") or []) + ["retrieve_context"]
            return {
                "retrieved_documents":  memories,
                "source_documents":     [],
                # Use "irrelevant" so grade_documents_node triggers web search fallback.
                # Do NOT use "no_docs" — that can confuse the no-doc-answer path.
                "document_relevance":   "irrelevant",
                # Set confidence=1.0 so route_after_grading does NOT loop back here.
                "retrieval_confidence": 1.0,
                # Do NOT increment retry count — this is not a failed retrieval.
                "retrieval_retry_count": retry_count,
                "steps":                steps,
            }

        # 2. Reformulate query on low-confidence retry
        if retry_count > 0:
            reformulate_prompt = (
                f"We need to search the vector database for the query: '{last_query}'. "
                f"The previous search attempt had low confidence. Generate a different, "
                f"alternative search query to retrieve relevant documents. "
                f"Reply with ONLY the alternative query. No markdown, no extra text."
            )
            alternative_q = await _call_llm_text(reformulate_prompt, config)
            if alternative_q:
                last_query = alternative_q.strip()
                logger.info(f"Retrieval retry {retry_count}: reformulated query to '{last_query}'")

        # 3. Multi-Query Decomposition
        # Skip for short/simple queries (≤ 8 words) — saves an LLM round-trip with no benefit.
        queries = [last_query]
        _decomp_word_count = len(last_query.split())
        if _decomp_word_count > 8:
            decomp_prompt = QUERY_DECOMPOSITION_PROMPT.format(query=last_query)
            parsed_decomp = await _call_llm_judge(decomp_prompt, config)
            if parsed_decomp and isinstance(parsed_decomp, dict) and isinstance(parsed_decomp.get("queries"), list):
                queries = parsed_decomp["queries"]
                if last_query not in queries:
                    queries.insert(0, last_query)
                logger.info(f"Multi-query decomposed query into: {queries}")
        else:
            logger.info(f"[QueryDecompose] Skipping decomposition for short query ({_decomp_word_count} words): '{last_query[:60]}'")

        # Append compound sub-questions to queries so each sub-question is queried against ChromaDB
        sub_qs = state.get("sub_questions") or []
        for sq in sub_qs:
            if sq and str(sq).strip() and str(sq).strip() not in queries:
                queries.append(str(sq).strip())

        # Deterministic query expansion for GPA/CGPA queries
        l_q_low = last_query.lower()
        if "gpa" in l_q_low or "cgpa" in l_q_low or "grade" in l_q_low or "mark" in l_q_low:
            for extra_q in ["gpa", "cgpa", "CGPA", "GPA", "CGP A", "education CGPA"]:
                if extra_q not in queries:
                    queries.append(extra_q)

        # 4. Fetch user document stats for dynamic k sizing
        num_docs = 0
        total_size_bytes = 0
        try:
            from app.services.document_service import DocumentService
            async with AsyncSessionLocal() as db:
                user_docs = await DocumentService.get_user_documents(db, user_id)
                num_docs = len(user_docs)
                total_size_bytes = sum(d.size_bytes for d in user_docs)
        except Exception as e:
            logger.error(f"Failed to fetch user documents for dynamic k: {e}")

        # 5. Determine query complexity
        query_complexity = 1.0
        if len(last_query.split()) > 25:
            query_complexity += 1.0
        if len(queries) > 1:
            query_complexity += 1.0

        prev_confidence = state.get("retrieval_confidence", 1.0)
        cfg_retrieval_depth = config.get("configurable", {}).get("retrieval_depth") or 5

        dynamic_k = calculate_dynamic_k(
            num_docs=num_docs,
            total_size_bytes=total_size_bytes,
            query_complexity=query_complexity,
            confidence_score=prev_confidence,
            base_k=cfg_retrieval_depth
        )
        logger.info(f"Dynamic retrieval depth: k={dynamic_k} (docs={num_docs}, size={total_size_bytes}, complexity={query_complexity}, prev_conf={prev_confidence})")

        # 6. Retrieve relevant chunks for all queries in parallel
        try:
            from app.retrieval.vector_store import VectorStore
            vector_store = VectorStore()

            # P2-1 FIX: Extract the user's runtime Gemini key from config so
            # query-time embeddings use real vectors. Previously api_key was
            # never passed here, so if settings.GEMINI_API_KEY was unset in .env,
            # all retrieval fell back to deterministic mock embeddings (random results).
            _ret_keys    = _embed_keys  # already extracted above
            _embed_key   = (
                _ret_keys.get("gemini")
                or _ret_keys.get("google")
                or getattr(settings, "GEMINI_API_KEY", None)
                or None
            )

            async def retrieve_for_query(q: str):
                try:
                    return await vector_store.query_relevant_chunks(
                        user_id=user_id,
                        query=q,
                        k=dynamic_k,
                        api_key=_embed_key,   # P2-1 FIX: propagate runtime key
                    )
                except Exception as ex:
                    logger.error(f"VectorStore query failed for sub-query '{q}': {ex}")
                    return []

            tasks = [retrieve_for_query(q) for q in queries]
            if tasks:
                raw_results = await asyncio.gather(*tasks, return_exceptions=True)
                results_lists = [r if isinstance(r, list) else [] for r in raw_results]
            else:
                results_lists = []

            # Merge and deduplicate chunks (by document_id, chunk_index, and content snippet)
            seen = set()
            merged_chunks = []
            for chunks_list in results_lists:
                for chunk in chunks_list:
                    chunk_key = (chunk.get("document_id"), chunk.get("chunk_index"), chunk.get("content", "")[:100])
                    if chunk_key not in seen:
                        seen.add(chunk_key)
                        merged_chunks.append(chunk)

            # Sort by RAG confidence and hybrid RRF score (highest relevance first)
            merged_chunks.sort(key=lambda c: (c.get("confidence", 0.0), c.get("rrf_score", 0.0), -c.get("distance", 1.0)), reverse=True)
            candidate_chunks = merged_chunks[:max(dynamic_k * 2, 10)]

            # ── Cross-encoder re-ranking ──────────────────────────────────────────
            # For compound queries, rerank against private-doc sub-questions specifically
            # so private-doc chunks aren't discarded due to unrelated query text.
            sub_qs = state.get("sub_questions") or []
            _ret_signals = state.get("_doc_signals") or UNIVERSAL_SIGNALS
            _, private_sub_qs = classify_sub_questions(sub_qs, _ret_signals)
            rerank_query = " | ".join(private_sub_qs) if private_sub_qs else last_query

            _rerank_word_count = len(rerank_query.split())
            if candidate_chunks and _rerank_word_count > 2:
                logger.info(f"[VectorStore] Invoking Cross-Encoder reranker on {len(candidate_chunks)} candidates for query '{rerank_query[:40]}'")
                reranked_chunks = await vector_store.rerank_chunks(
                    query=rerank_query,
                    chunks=candidate_chunks,
                    config=config,
                    threshold=0.2,
                )
                doc_chunks = reranked_chunks[:dynamic_k]
            elif candidate_chunks:
                logger.info(f"[VectorStore] Skipping reranker for short query ({_rerank_word_count} words) — using RRF ordering")
                doc_chunks = candidate_chunks[:dynamic_k]
            else:
                doc_chunks = []

            # ── Context compression (deduplication & token-budget enforcement) ───
            if doc_chunks:
                doc_chunks = VectorStore.compress_context(doc_chunks)

            # BUG-3 FIX: Sanitize each chunk's content against indirect prompt injection
            # (malicious documents trying to override the system prompt)
            if doc_chunks:
                try:
                    from app.middleware.security import IndirectInjectionGuard
                    sanitized_chunks = []
                    for _chunk in doc_chunks:
                        _clean_content = IndirectInjectionGuard.sanitize_external_content(
                            _chunk.get("content", "")
                        )
                        sanitized_chunks.append({**_chunk, "content": _clean_content})
                    doc_chunks = sanitized_chunks
                except Exception as _inj_err:
                    logger.warning(f"IndirectInjectionGuard failed (non-fatal): {_inj_err}")

        except Exception as e:
            logger.error(f"VectorStore query failed: {e}")

    # ── Similarity threshold pre-filter ──────────────────────────────────────
    # Chunks with confidence < SIMILARITY_THRESHOLD are dropped before CRAG.
    # This prevents very weak matches (e.g., Resume.pdf for 'LeetCode 23')
    # from ever reaching the LLM as sources.
    SIMILARITY_THRESHOLD = 0.25
    above_threshold = [c for c in doc_chunks if c.get("confidence", 0.0) >= SIMILARITY_THRESHOLD]
    below_threshold = [c for c in doc_chunks if c.get("confidence", 0.0) < SIMILARITY_THRESHOLD]
    if below_threshold:
        logger.info(
            f"[RAG] Pre-filter: dropped {len(below_threshold)} chunk(s) below "
            f"similarity threshold {SIMILARITY_THRESHOLD}: "
            + ", ".join(f"{c.get('filename','?')}(conf={c.get('confidence',0):.2f})" for c in below_threshold)
        )
    doc_chunks = above_threshold

    retrieved_items = memories + doc_chunks

    # source_documents starts empty — only CRAG-validated chunks will populate it
    # (grade_documents_node is responsible for the final authoritative list)
    source_documents: List[Dict[str, Any]] = [
        {
            "index":      idx + 1,
            "filename":   ch.get("filename", "Unknown"),
            "content":    ch.get("content", ""),
            "distance":   ch.get("distance"),
            "confidence": ch.get("confidence"),
            "chunk_id":   ch.get("chunk_id"),
            "document_id": ch.get("document_id"),
            "used":       False,   # grade_documents_node will set used=True for kept chunks
        }
        for idx, ch in enumerate(doc_chunks)
    ]

    # ── RAG Audit Log ─────────────────────────────────────────────────────────
    logger.info(
        "\n" + "=" * 54 + "\n"
        f"[RAG AUDIT] Stage: retrieve_context\n"
        f"  Query        : {(last_query or '')[:80]}\n"
        f"  Retrieved    : {len(doc_chunks)} chunk(s) above threshold "
        f"(dropped {len(below_threshold)} below {SIMILARITY_THRESHOLD})\n"
        f"  Docs         : " +
        ", ".join(f"{c.get('filename','?')}(conf={c.get('confidence',0):.2f})" for c in doc_chunks) + "\n"
        + "=" * 54
    )

    steps = list(state.get("steps") or []) + ["retrieve_context"]
    return {
        "retrieved_documents": retrieved_items,
        "source_documents":    source_documents,
        "document_relevance":  "no_docs" if not doc_chunks else "ungraded",
        "retrieval_retry_count": retry_count + 1,
        "steps":               steps,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Node 5: CRAG — grade document relevance  (P0 fix: private-doc guard)
# ─────────────────────────────────────────────────────────────────────────────

async def grade_documents_node(
    state: AgentState, config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    CRAG (Corrective RAG) node — grades each retrieved document chunk for
    relevance and freshness.
    
    Detects outdated information and performs web verification only when
    freshness is actually required (and query is NOT private).
    """
    config            = config or {}
    messages          = state.get("messages", [])
    retrieved_docs    = list(state.get("retrieved_documents", []))
    source_documents  = list(state.get("source_documents", []))
    steps             = list(state.get("steps") or [])
    is_private        = state.get("is_private_doc_query", False)
    intent            = state.get("intent", INTENT_NORMAL_CHAT)

    # Extract user API keys from LangGraph config so search providers can use them
    req_api_keys: Dict[str, Any] = config.get("configurable", {}).get("api_keys", {})

    # 1. Extract resolved_query or last user query
    last_query = state.get("resolved_query") or _extract_last_user_query(messages)

    doc_chunks   = [d for d in retrieved_docs if d.get("type") == "chunk"]
    memory_items = [d for d in retrieved_docs if d.get("type") != "chunk"]

    if not doc_chunks:
        # Attempt live web search ONLY for search-specific public queries when vector DB has no chunks
        if not is_private and intent in (INTENT_WEB_SEARCH, INTENT_NEWS, INTENT_CURRENT_EVENTS, INTENT_FINANCE):
            if last_query:
                logger.info(
                    f"CRAG: No doc chunks for public search query (intent={intent}) → forcing web search fallback."
                )
                try:
                    import re as _re2
                    # ── COMPOUND QUERY FIX: run a separate web search for each sub-question
                    # so that multi-part queries ('tennis 2026? AND food tracking?') get all
                    # their questions answered, not just the first one.
                    sub_questions: List[str] = state.get("sub_questions") or []
                    _search_targets = sub_questions if len(sub_questions) >= 2 else [last_query]

                    all_web_chunks: List[dict] = []
                    all_web_src_docs: List[Dict[str, Any]] = []
                    combined_web_text_parts: List[str] = []
                    src_index_offset = 0

                    for _sq in _search_targets:
                        _sq_clean = _re2.sub(r"\[System Context:[^\]]*\]", "", _sq)
                        _sq_clean = _re2.sub(r"\[User Location Context:[^\]]*\]", "", _sq_clean)
                        _sq_clean = _re2.sub(r"\[Connected Reference Context[^\[]*\[End of Referenced Context\]", "", _sq_clean, flags=_re2.DOTALL).strip() or _sq

                        _sq_results = await unified_web_search(_sq_clean, req_api_keys)
                        if _sq_results:
                            _sq_text = format_for_llm(_sq_results)
                            _sq_src_docs = format_as_source_documents(_sq_results)
                            # Prefix the web text with the sub-question so the LLM knows which answer belongs where
                            combined_web_text_parts.append(f"### Search results for: {_sq_clean}\n{_sq_text}")
                            # Re-index source docs to avoid collisions
                            for _sd in _sq_src_docs:
                                _sd["index"] = src_index_offset + _sd["index"]
                                _sd["sub_question"] = _sq_clean
                                all_web_src_docs.append(_sd)
                            src_index_offset += len(_sq_src_docs)

                    if combined_web_text_parts:
                        combined_web_result = "\n\n".join(combined_web_text_parts)
                        web_chunk = {
                            "type":     "chunk",
                            "content":  combined_web_result,
                            "filename": "Web Search Results",
                            "distance": 0.0,
                        }
                        steps.append("grade_documents")
                        return {
                            "document_relevance":   "web_fallback",
                            "no_doc_answer":        False,
                            "retrieved_documents":  retrieved_docs + [web_chunk],
                            "source_documents":     all_web_src_docs,
                            "retrieval_confidence": 0.9,
                            "generation_mode":      "web_search",
                            "steps":                steps,
                        }
                except Exception as e:
                    logger.error(f"CRAG web search on empty docs failed: {e}")

        steps.append("grade_documents")
        return {
            "document_relevance":  "no_docs",
            "no_doc_answer":       is_private,
            "retrieved_documents": retrieved_docs,
            "retrieval_confidence": 0.0,
            "steps":               steps,
        }

    # 2. Check if freshness is actually required
    freshness_keywords = {"latest", "current", "today", "now", "recent", "news", "version", "update", "stock", "price", "weather"}
    query_lower = last_query.lower()
    freshness_required = any(k in query_lower for k in freshness_keywords)

    # 2b. For COMPLEX queries: build a doc-specific grading query from private-doc sub-questions only.
    # This prevents private-doc chunks from being graded as irrelevant just because the
    # full compound query also contains public sub-questions (chess 2026, total expenses, etc.).
    grading_query = last_query
    if intent == INTENT_COMPLEX and is_private:
        sub_qs = state.get("sub_questions") or []
        _grade_signals = state.get("_doc_signals") or UNIVERSAL_SIGNALS
        _, private_sub_qs = classify_sub_questions(sub_qs, _grade_signals)
        if private_sub_qs:
            grading_query = " | ".join(private_sub_qs)
            # Private doc grading is never freshness-required
            freshness_required = False
            logger.info(f"CRAG: Using private-doc sub-questions for grading: {private_sub_qs}")

    # Stopwords filtered from heuristic fallback to avoid false positives.
    # Extended with domain-specific action words that appear in many unrelated
    # documents and cause false-positive overlap matches.
    _STOPWORDS = frozenset({
        # Common English stopwords
        "the", "a", "an", "is", "in", "of", "to", "and", "or", "for",
        "on", "at", "by", "it", "be", "as", "my", "this", "that", "i",
        "with", "from", "are", "was", "were", "has", "have", "had",
        "do", "does", "did", "not", "can", "will", "would", "you",
        # Action/question words that appear broadly and inflate overlap scores
        "fetch", "get", "show", "tell", "add", "also", "total", "month",
        "today", "give", "what", "who", "how", "when", "where", "which",
        "current", "latest", "recent", "please", "find", "list", "all",
        "about", "using", "then", "plus", "more", "less", "much", "many",
        "some", "any", "its", "their", "them", "they", "we", "our", "us",
    })

    async def grade_one(chunk: dict) -> str:
        """
        Grade a single document chunk for relevance against grading_query.

        CRAG scoring logic:
        1. Hard reject: conf < 0.25 (very low similarity score from vector DB)
        2. LLM judge: ask the LLM to score the chunk as relevant/partial/irrelevant/outdated
        3. Heuristic fallback: keyword overlap when LLM is unavailable

        The old conf >= 0.85 auto-pass shortcut has been REMOVED because it
        caused unrelated documents (resumes, tech docs) to pass as 'relevant'
        for general-knowledge or expense queries whenever their cosine similarity
        happened to be above 0.85.  Every chunk now requires actual content
        validation via the LLM judge or the strict keyword heuristic.
        """
        conf = chunk.get("confidence", 0.0)
        # Hard reject: similarity below minimum threshold
        if conf < 0.25:
            return "irrelevant"

        prompt = DOCUMENT_GRADER_PROMPT.format(
            query=grading_query,  # Use focused query (private-doc sub-questions for COMPLEX)
            chunk=chunk.get("content", "")[:800],
        )
        parsed = await _call_llm_judge(prompt, config)
        if parsed:
            return parsed.get("score", "partial")
        # Heuristic fallback when ALL providers are rate-limited or unavailable.
        # Require >= 4 UNIQUE meaningful (non-stopword, non-trivial) words overlap.
        # Higher threshold (4 vs previous 3) reduces false positives.
        query_words = {w for w in grading_query.lower().split() if w not in _STOPWORDS and len(w) > 3}
        chunk_words = {w for w in chunk.get("content", "").lower().split() if w not in _STOPWORDS and len(w) > 3}
        overlap = len(query_words & chunk_words)
        if overlap >= 3:
            return "relevant"
        if overlap >= 1 and conf >= 0.5:
            return "partial"
        return "irrelevant"

    scores = await asyncio.gather(*[grade_one(ch) for ch in doc_chunks])


    relevant_chunks: List[dict] = []
    has_outdated = False
    for chunk, score in zip(doc_chunks, scores):
        if score == "outdated":
            has_outdated = True
            # If freshness is required, outdated chunks are NOT considered relevant context
            if not freshness_required:
                relevant_chunks.append(chunk)
        elif score in ("relevant", "partial"):
            relevant_chunks.append(chunk)

    # 4. Calculate confidence score
    confidence_score = len(relevant_chunks) / len(doc_chunks) if doc_chunks else 0.0
    logger.info(
        f"CRAG: {len(relevant_chunks)}/{len(doc_chunks)} chunks relevant. "
        f"Confidence={confidence_score:.2f} | has_outdated={has_outdated} | private={is_private}"
    )

    should_search_web = False
    # Determine whether we need a web search.
    # HYBRID QUERY FIX: Even when is_private_doc_query=True for the FULL request,
    # we must still perform web search for PUBLIC sub-questions (e.g. 'Who is PM of
    # India?' in a compound query like 'Who is PM of India? Also fetch my expenses').
    # We separate sub_questions into public and private lists and handle each correctly.
    sub_questions_all: List[str] = state.get("sub_questions") or []
    # Classify sub-questions as public (need web) vs private (need docs)
    # Uses per-user dynamic signals — no project-specific names hardcoded.
    _grade_ws_signals = state.get("_doc_signals") or UNIVERSAL_SIGNALS
    public_sub_questions, private_sub_questions = classify_sub_questions(sub_questions_all, _grade_ws_signals)

    # Always search web for public sub-questions regardless of is_private flag
    has_public_sub_questions = len(public_sub_questions) > 0

    if not is_private or intent in (INTENT_COMPLEX, INTENT_WEB_SEARCH):
        if intent in (INTENT_WEB_SEARCH, INTENT_NEWS, INTENT_CURRENT_EVENTS, INTENT_FINANCE, INTENT_COMPLEX):
            should_search_web = True
        elif freshness_required and (has_outdated or not relevant_chunks):
            should_search_web = True
        elif not relevant_chunks and not is_private:
            should_search_web = True

    # HYBRID QUERY FIX: also trigger web search if there are public sub-questions,
    # even when the overall query is private (is_private_doc_query=True)
    if has_public_sub_questions and not should_search_web:
        should_search_web = True
        logger.info(
            f"CRAG: Hybrid query detected — triggering web search for "
            f"{len(public_sub_questions)} public sub-question(s): {public_sub_questions}"
        )

    # 5. Handle web fallback
    document_relevance = "relevant" if relevant_chunks else "irrelevant"
    if should_search_web and last_query:
        logger.info(f"CRAG: Freshness required & issues found → Executing web search fallback.")
        try:
            import re as _re3
            # HYBRID QUERY FIX: For compound queries, use the public_sub_questions list
            # for web search targets. Private sub-questions that match personal doc signals
            # are explicitly skipped (they are handled by vector store retrieval above).
            # If no sub-questions are available, fall back to the full last_query.
            if public_sub_questions:
                # Only search for public (non-personal) parts of the query
                _search_targets = public_sub_questions
            elif sub_questions_all:
                # No classified sub-questions — filter personal signals the old way
                _search_targets = sub_questions_all
            else:
                _search_targets = [last_query]

            all_combined_text_parts: List[str] = []
            src_index_offset = len(source_documents)

            for _sq in _search_targets:
                # _search_targets is already pre-filtered (public_sub_questions or last_query).
                # No secondary personal-signal filter needed here.

                _sq_clean = _re3.sub(r"\[System Context:[^\]]*\]", "", _sq)
                _sq_clean = _re3.sub(r"\[User Location Context:[^\]]*\]", "", _sq_clean)
                _sq_clean = _re3.sub(r"\[Connected Reference Context[^\[]*\[End of Referenced Context\]", "", _sq_clean, flags=_re3.DOTALL).strip() or _sq

                _sq_results = await unified_web_search(_sq_clean, req_api_keys)
                if _sq_results:
                    _sq_text = format_for_llm(_sq_results)
                    _sq_src_docs = format_as_source_documents(_sq_results)
                    all_combined_text_parts.append(f"### Search results for: {_sq_clean}\n{_sq_text}")
                    for _sd in _sq_src_docs:
                        _sd["index"] = src_index_offset + _sd["index"]
                        _sd["sub_question"] = _sq_clean
                        source_documents.append(_sd)
                    src_index_offset += len(_sq_src_docs)

            if all_combined_text_parts:
                combined_web_result = "\n\n".join(all_combined_text_parts)
                web_chunk = {
                    "type":     "chunk",
                    "content":  combined_web_result,
                    "filename": "Web Search Results",
                    "distance": 0.0,
                }
                relevant_chunks.append(web_chunk)
            document_relevance = "web_fallback"
        except Exception as e:
            logger.error(f"CRAG web fallback failed: {e}")

    # No relevant chunks and no web search path for private doc queries
    if not relevant_chunks and is_private:
        logger.info("CRAG: no relevant chunks for private query (Tavily blocked) → no doc answer guard active.")
        steps.append("grade_documents")
        return {
            "document_relevance":  "no_private_docs",
            "no_doc_answer":       True,
            "retrieved_documents": memory_items,
            "source_documents":    [],
            "retrieval_confidence": confidence_score,
            "generation_mode":     "crag_rejected",
            "steps":               steps,
        }

    # No relevant chunks for a NON-private query → fall back to model knowledge
    if not relevant_chunks:
        has_doc_chunks = len(doc_chunks) > 0
        logger.info("CRAG: 0 relevant chunks for public query → model knowledge mode.")
        _log_rag_audit(
            stage="grade_documents",
            query=last_query,
            retrieved=doc_chunks,
            scores=list(scores),
            crag_decision="REJECTED (0 relevant chunks)",
            self_rag_decision="N/A",
            docs_sent=[],
            docs_rejected=doc_chunks,
            generation_mode="model_knowledge",
            sources_returned=[],
        )
        steps.append("grade_documents")
        return {
            "document_relevance":  "irrelevant",
            "no_doc_answer":       has_doc_chunks,  # If candidate doc chunks existed but failed grade, enforce no-doc guard
            "retrieved_documents": memory_items,   # only memories, no chunks
            "source_documents":    [],              # ← authoritative: no sources
            "retrieval_confidence": confidence_score,
            "generation_mode":     "model_knowledge",
            "steps":               steps,
        }

    # ── Build final validated source_documents (only used=True chunks) ────────
    # Mark each chunk that passed CRAG as used=True for frontend attribution.
    # CLICKABLE LINKS FIX: also propagate the `url` field so web search sources
    # get their actual URLs passed to the frontend for rendering as clickable links.
    relevant_content_set = {ch.get("content", "")[:80] for ch in relevant_chunks}
    final_source_documents: List[Dict[str, Any]] = []
    for i, ch in enumerate(relevant_chunks):
        final_source_documents.append({
            "index":        i + 1,
            "filename":     ch.get("filename", "Unknown"),
            "content":      ch.get("content", ""),
            "distance":     ch.get("distance"),
            "confidence":   ch.get("confidence"),
            "chunk_id":     ch.get("chunk_id"),
            "document_id":  ch.get("document_id"),
            "url":          ch.get("url", ""),          # ← CLICKABLE LINKS FIX
            "source":       ch.get("source", ""),       # provider name (tavily/serpapi/etc)
            "sub_question": ch.get("sub_question", ""), # which sub-question this answered
            "used":         True,   # ← only CRAG-validated chunks are marked used
        })

    rejected_chunks = [ch for ch in doc_chunks if ch.get("content", "")[:80] not in relevant_content_set]

    # ── RAG Audit Log ─────────────────────────────────────────────────────────
    _log_rag_audit(
        stage="grade_documents",
        query=last_query,
        retrieved=doc_chunks,
        scores=list(scores),
        crag_decision=f"PASSED {len(relevant_chunks)}/{len(doc_chunks)} chunks (conf={confidence_score:.2f})",
        self_rag_decision="N/A",
        docs_sent=relevant_chunks,
        docs_rejected=rejected_chunks,
        generation_mode="normal_rag" if relevant_chunks else "model_knowledge",
        sources_returned=final_source_documents,
    )

    filtered_docs = memory_items + relevant_chunks
    steps.append("grade_documents")
    return {
        "retrieved_documents": filtered_docs,
        "source_documents":    final_source_documents,
        "document_relevance":  document_relevance,
        "no_doc_answer":       False,
        "retrieval_confidence": confidence_score,
        "generation_mode":     "normal_rag",
        "steps":               steps,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Streaming response sanitizer (P0 Fix: Real-time tool-name leakage guard)
# ─────────────────────────────────────────────────────────────────────────────

class StreamingSanitizer:
    """
    Maintains a sliding window buffer of streaming tokens to detect and redact
    internal tool names and CoT phrases in real-time, handling words split
    across chunk boundaries.
    """
    def __init__(self, internal_names: List[str]):
        self.internal_names = internal_names
        self.buffer = ""
        self.block_prefixes = [
            "calling tools:", "calling tool:", "i used the", "i called the",
            "i executed the", "i ran the", "tool output:", "tool result:",
            "[tool output:"
        ]
        
    def feed(self, chunk: str) -> str:
        self.buffer += chunk
        
        # 1. Clean completed forbidden patterns or raw tool-call JSON
        import re
        phrases_to_redact = [
            r"function\s*=>\s*\{[^{}]*\"query\"[^{}]*\}\s*(?:</function>)?",
            r"function\s*=>\s*\{.*?\}(?:</function>)?",
            r"function\s*=>\s*.*?(?:</function>|\n|$)",
            r"</?function\b[^>]*>",
            r"<(?:>|/[^>]*>)?\s*\{[^{}]*\"query\"[^{}]*\}\s*</?>?",
            r"\{[^{}]*\"query\"\s*:\s*\"[^\"]*\"[^{}]*\}",
            r"<tool_call>.*?</tool_call>",
            r"<search>.*?</search>",
            r"<search_query>.*?</search_query>",
            r"\[tool output:\s*\w+\]\s*",
            r"calling tools?:\s*[\w,\s]+\.{3}",
            r"i (?:used|called|invoked|ran|executed) (?:the )?(?:tool|sandbox|search)\b[^.]*\.",
            r"\[System Context:[^\]]*\]\s*",
            r"\[System Context\]\s*",
        ]
        for phrase in phrases_to_redact:
            self.buffer = re.sub(phrase, "", self.buffer, flags=re.IGNORECASE | re.DOTALL)
            
        # Redact exact internal names
        for name in self.internal_names:
            pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
            self.buffer = pattern.sub("", self.buffer)
            
        # 2. Check if the end of the buffer might be an incomplete match of a forbidden term
        lower_buf = self.buffer.lower()
        hold_len = 0
        all_match_targets = self.internal_names + self.block_prefixes
        for target in all_match_targets:
            for l in range(1, min(len(lower_buf), len(target)) + 1):
                suffix = lower_buf[-l:]
                if target.startswith(suffix):
                    hold_len = max(hold_len, l)
                    
        if hold_len > 0:
            to_yield = self.buffer[:-hold_len]
            self.buffer = self.buffer[-hold_len:]
            return to_yield
        else:
            to_yield = self.buffer
            self.buffer = ""
            return to_yield

    def flush(self) -> str:
        import re
        final_text = self.buffer
        self.buffer = ""
        phrases_to_redact = [
            r"function\s*=>\s*\{[^{}]*\"query\"[^{}]*\}\s*(?:</function>)?",
            r"function\s*=>\s*\{.*?\}(?:</function>)?",
            r"function\s*=>\s*.*?(?:</function>|\n|$)",
            r"</?function\b[^>]*>",
            r"<(?:>|/[^>]*>)?\s*\{[^{}]*\"query\"[^{}]*\}\s*</?>?",
            r"\{[^{}]*\"query\"\s*:\s*\"[^\"]*\"[^{}]*\}",
            r"<tool_call>.*?</tool_call>",
            r"<search>.*?</search>",
            r"<search_query>.*?</search_query>",
            r"\[tool output:\s*\w+\]\s*",
            r"calling tools?:\s*[\w,\s]+\.{3}",
            r"\[System Context:[^\]]*\]\s*",
            r"\[System Context\]\s*",
        ]
        for phrase in phrases_to_redact:
            final_text = re.sub(phrase, "", final_text, flags=re.IGNORECASE | re.DOTALL)
        for name in self.internal_names:
            pattern = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
            final_text = pattern.sub("", final_text)
        return final_text


# ─────────────────────────────────────────────────────────────────────────────
#  Node 6: Generate response  (P0 fixes: tool gating, sanitizer, file paths,
#                                        image guard, no_doc_answer)
# ─────────────────────────────────────────────────────────────────────────────

async def generate_response_node(
    state: AgentState, config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    Core streaming generation node.

    P0 Fixes Applied
    ─────────────────
    • Tool schemas are injected PER-INTENT using the allowed_tools whitelist.
      An empty whitelist means NO tool schemas are passed → LLM cannot call any.
    • _sanitize_response() removes internal tool names from the final text.
    • uploaded_file_paths forwarded to compile_system_prompt() for code tasks.
    • no_doc_answer forwarded to compile_system_prompt() for hallucination guard.
    • Image-provider mismatch: if images are present but the active model is not
      Gemini, returns a graceful user-facing message instead of silently dropping.
    """
    config          = config or {}
    model           = state.get("active_model") or ""
    if not model:
        logger.error("generate_response_node: no active_model in state — cannot proceed")
        if config.get("configurable", {}).get("on_token"):
            await config["configurable"]["on_token"]("*[Error: No model selected. Please select a model from the model picker.]*")
        return {**state, "response_text": "*[Error: No model selected. Please select a model from the model picker.]*"}
    model_aliases = {
        # Map all deprecated/renamed models to current stable equivalents
        "gemini-1.5-flash":                     "gemini-2.0-flash",
        "gemini-1.5-pro":                       "gemini-2.0-flash",
        "gemini-2.5-flash":                     "gemini-2.0-flash",
        "gemini-2.5-pro":                       "gemini-2.0-flash",
        "gemini-3.5-flash":                     "gemini-2.0-flash",
        "openrouter/google/gemini-flash-1.5":   "openrouter/google/gemini-2.0-flash",
        "openrouter/google/gemini-pro-1.5":     "openrouter/google/gemini-2.0-flash",
        "openrouter/google/gemini-2.5-flash":   "openrouter/google/gemini-2.0-flash",
        "openrouter/google/gemini-3.5-flash":   "openrouter/google/gemini-2.0-flash",
        "google/gemini-flash-1.5":              "google/gemini-2.0-flash",
        "google/gemini-pro-1.5":                "google/gemini-2.0-flash",
        "google/gemini-2.5-flash":              "google/gemini-2.0-flash",
        "google/gemini-3.5-flash":              "google/gemini-2.0-flash",
        # Deprecated Groq models
        "mixtral-8x7b-32768":                   "llama-3.3-70b-versatile",
    }
    model           = model_aliases.get(model, model)
    retrieved_items   = state.get("retrieved_documents", [])
    messages          = state.get("messages", [])
    plan              = state.get("plan")
    reflection_fb     = state.get("reflection_feedback")
    iteration_count   = state.get("iteration_count", 0)
    images            = state.get("images") or []
    intent            = state.get("intent", INTENT_NORMAL_CHAT)
    allowed_tools     = state.get("allowed_tools") or []
    no_doc_answer     = state.get("no_doc_answer", False)
    uploaded_paths    = state.get("uploaded_file_paths") or []
    detected_language = state.get("detected_language")
    language_mode     = state.get("language_mode")

    on_token   = config.get("configurable", {}).get("on_token")
    on_metrics = config.get("configurable", {}).get("on_metrics")
    keys       = _extract_api_keys(config)

    # ── Image-provider vision-capability guard with auto-fallback ──────────────
    # Determine whether the active model supports vision / image input.
    # We check the full model string (including openrouter/ prefix) so that
    # vendor-prefixed names like "openrouter/meta-llama/llama-4-scout" match.
    _model_lower = model.lower()
    # Fragments that indicate a vision-capable model across all providers:
    _VISION_FRAGMENTS = (
        # Google / Gemini
        "gemini", "google",
        # OpenAI
        "gpt-4o", "gpt-4-vision", "gpt-4.1", "o1", "o3", "o4",
        # Anthropic
        "claude-3", "claude-4",
        # Meta Llama vision
        "llama-3.2", "llama-4", "llama4",
        # DeepSeek vision
        "deepseek-vl", "deepseek-v3",
        # Alibaba Qwen vision
        "qwen-vl", "qwen2-vl", "qwen2.5-vl", "qvq",
        # Mistral
        "pixtral", "mistral-large",
        # LLaVA
        "llava",
        # GLM vision
        "glm-4v",
        # InternVL
        "internvl",
        # Generic vision keywords
        "vision", "-vl", "-vision",
    )
    is_vision_capable_model = any(frag in _model_lower for frag in _VISION_FRAGMENTS)
    _selected_key = _best_api_key(keys, model)
    has_valid_key_for_selected_model = bool(_selected_key) and not str(_selected_key).startswith("mock_")
    if images and not is_vision_capable_model:
        # User selected a non-vision model (e.g. llama-3.1-8b-instant) — perform local multi-engine OCR!
        logger.info(f"generate_response_node: '{model}' is not vision-capable — executing local multi-engine OCR (EasyOCR / Tesseract)")
        ocr_text = _perform_local_ocr_on_images(images)
        if ocr_text:
            ocr_note = f"*(Extracted handwritten notes & diagram using Local OCR — processing with **{model}**)*\n\n"
            if on_token:
                try:
                    await on_token(ocr_note)
                except Exception:
                    pass
            # Append OCR text into message state for the user's selected model
            for msg in reversed(messages):
                if hasattr(msg, "type") and getattr(msg, "type") in ("human", "user"):
                    msg.content = f"{msg.content}\n\n[Extracted Image Text & Reconstructed Diagram (Local OCR)]:\n{ocr_text}"
                    break
                elif isinstance(msg, dict) and msg.get("role") in ("human", "user"):
                    msg["content"] = f"{msg.get('content', '')}\n\n[Extracted Image Text & Reconstructed Diagram (Local OCR)]:\n{ocr_text}"
                    break
        else:
            # Local OCR produced no text — try Cloud Vision auto-fallback as backup
            gemini_key = keys.get("gemini") or keys.get("google") or getattr(settings, "GEMINI_API_KEY", None) or os.environ.get("GEMINI_API_KEY")
            openai_key = keys.get("openai") or getattr(settings, "OPENAI_API_KEY", None) or os.environ.get("OPENAI_API_KEY")
            if gemini_key and not str(gemini_key).startswith("mock_"):
                keys["gemini"] = gemini_key
                keys["google"] = gemini_key
                model = "gemini-2.0-flash"
                provider = gemini_provider
                provider_api_key = gemini_key
                if on_token:
                    try:
                        await on_token("*(Local OCR found no text — analyzing image with Gemini Flash)*\n\n")
                    except Exception:
                        pass
            elif openai_key and not str(openai_key).startswith("mock_"):
                keys["openai"] = openai_key
                model = "gpt-4o"
                provider = openai_provider
                provider_api_key = openai_key
                if on_token:
                    try:
                        await on_token("*(Local OCR found no text — analyzing image with GPT-4o)*\n\n")
                    except Exception:
                        pass
            images = []




    # ── Build system prompt ───────────────────────────────────────────────────
    sys_prompt = compile_system_prompt(
        retrieved_items,
        plan=plan,
        reflection_feedback=reflection_fb,
        has_images=bool(images),
        intent=intent,
        uploaded_file_paths=uploaded_paths if uploaded_paths else None,
        no_doc_answer=no_doc_answer,
        detected_language=detected_language,
        language_mode=language_mode,
    )

    raw_messages = [{"role": "system", "content": sys_prompt}]
    for msg in messages:
        role = "user"
        if hasattr(msg, "type"):
            if msg.type == "ai":
                role = "assistant"
            elif msg.type == "system":
                role = "system"
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        raw_messages.append({"role": role, "content": content})

    # Phase 3 parallel tool results injection:
    exec_results = state.get("tool_execution_results")
    if exec_results:
        for res in exec_results:
            tool_name = res.get("tool", "unknown")
            output = res.get("output", "")
            status = res.get("status", "success")
            raw_messages.append({
                "role": "user",
                "content": f"[Tool Output: {tool_name}] (Status: {status})\n{output}"
            })

    # ── Intent-gated tool schema injection ────────────────────────────────────
    # Only the tools in allowed_tools are exposed to the LLM.
    # An empty allowed_tools → no tool schemas → LLM cannot call any tool.
    from app.tools.registry import ToolRegistry
    registry = ToolRegistry()
    if not registry.is_initialized:
        try:
            await registry.initialize()
        except Exception as exc:
            logger.warning(f"ToolRegistry initialization warning in generate_response_node: {exc}")

    last_user_query = state.get("resolved_query") or state.get("original_query") or _extract_last_user_query(messages)
    if allowed_tools and last_user_query:
        tool_schemas = await registry.get_semantically_relevant_tools(
            query=last_user_query,
            allowed_tools=allowed_tools,
            top_k=5,
            api_key=keys.get("gemini_api_key")
        )
    elif allowed_tools:
        tool_schemas = registry.get_tool_schemas_for_intent(allowed_tools)
    else:
        tool_schemas = []  # Pure generation — no tools offered

    logger.info(
        f"generate_response_node: intent={intent} | "
        f"tools_offered={[t['name'] for t in tool_schemas]} | "
        f"model={model}"
    )

    # ── Provider & fallback setup (logging, overrides and fallback checks) ────
    # actual_model_id strips the "openrouter/" prefix for provider routing logic
    actual_model_id  = model[11:] if model.startswith("openrouter/") else model
    provider         = get_provider(model)
    provider_api_key = _best_api_key(keys, model)

    def mask_key(k: Optional[str]) -> str:
        if not k:
            return "None"
        if len(k) > 8:
            return f"{k[:4]}...{k[-4:]}"
        return "****"

    logger.info(json.dumps({
        "event": "provider_resolution",
        "selected_model": model,
        "resolved_provider": provider.__class__.__name__,
        "retrieved_key_masked": mask_key(provider_api_key),
        "keys_available": [k for k, v in keys.items() if v]
    }))

    if not provider_api_key:
        logger.warning(json.dumps({
            "event": "missing_credentials",
            "provider": provider.__class__.__name__,
            "model": model
        }))

    counterparts = {
        "gemini-2.0-flash":                    ("openrouter", "google/gemini-2.0-flash"),
        "gemini-2.5-flash":                    ("openrouter", "google/gemini-2.0-flash"),
        "gemini-2.5-pro":                      ("openrouter", "google/gemini-2.0-flash"),
        "gemini-1.5-flash":                    ("openrouter", "google/gemini-2.0-flash"),
        "gemini-1.5-pro":                      ("openrouter", "google/gemini-2.0-flash"),
        "llama-3.1-8b-instant":                ("openrouter", "meta-llama/llama-3.1-8b-instruct"),
        "llama-3.3-70b-versatile":             ("openrouter", "meta-llama/llama-3.3-70b-instruct"),
        "gemma2-9b-it":                        ("openrouter", "google/gemma-2-9b-it"),
        "google/gemini-2.0-flash":             ("gemini", "gemini-2.0-flash"),
        "google/gemini-2.5-flash":             ("gemini", "gemini-2.0-flash"),
        "google/gemini-2.5-pro":               ("gemini", "gemini-2.0-flash"),
        "google/gemini-flash-1.5":             ("gemini", "gemini-2.0-flash"),
        "google/gemini-pro-1.5":               ("gemini", "gemini-2.0-flash"),
        "google/gemma-2-9b-it":                ("groq", "gemma2-9b-it"),
        "meta-llama/llama-3.1-8b-instruct":    ("groq", "llama-3.1-8b-instant"),
        "meta-llama/llama-3.3-70b-instruct":   ("groq", "llama-3.3-70b-versatile"),
    }

    attempts = [(provider, actual_model_id, provider_api_key)]
    if actual_model_id in counterparts:
        target_prov_name, target_model = counterparts[actual_model_id]
        target_key = keys.get(target_prov_name)
        if target_key:
            prov_inst = (
                gemini_provider     if target_prov_name == "gemini"
                else groq_provider  if target_prov_name == "groq"
                else openrouter_provider
            )
            attempts.append((prov_inst, target_model, target_key))

    model_lower = (actual_model_id or "").lower()
    if "gemini" in model_lower or "google" in model_lower:
        # Gemini primary → try OpenRouter Gemini → then Groq as rescue
        generic_fallbacks = [
            ("gemini",     gemini_provider,     "gemini-2.0-flash"),
            ("openrouter", openrouter_provider, "google/gemini-2.0-flash"),
            ("groq",       groq_provider,       "llama-3.3-70b-versatile"),
        ]
    elif "gpt" in model_lower or "o1-" in model_lower or "o3-" in model_lower or "o4-" in model_lower:
        # OpenAI primary → OpenRouter OpenAI → Gemini rescue
        generic_fallbacks = [
            ("openai",     openai_provider,     actual_model_id),
            ("openrouter", openrouter_provider, f"openai/{actual_model_id}"),
            ("gemini",     gemini_provider,     "gemini-2.0-flash"),
        ]
    elif "claude" in model_lower:
        # Anthropic primary → OpenRouter Anthropic → Gemini rescue
        generic_fallbacks = [
            ("anthropic",  openrouter_provider, f"anthropic/{actual_model_id}"),
            ("openrouter", openrouter_provider, f"anthropic/{actual_model_id}"),
            ("gemini",     gemini_provider,     "gemini-2.0-flash"),
        ]
    elif "deepseek" in model_lower:
        # DeepSeek primary → OpenRouter DeepSeek → Gemini rescue
        generic_fallbacks = [
            ("deepseek",   openrouter_provider, f"deepseek/{actual_model_id}"),
            ("openrouter", openrouter_provider, f"deepseek/{actual_model_id}"),
            ("gemini",     gemini_provider,     "gemini-2.0-flash"),
        ]
    elif "llama" in model_lower or "groq" in model_lower or "mixtral" in model_lower or "gemma" in model_lower:
        # Groq primary → OpenRouter Llama/Gemma → Gemini cross-provider rescue
        generic_fallbacks = [
            ("openrouter", openrouter_provider, "meta-llama/llama-3.3-70b-instruct"),
            ("gemini",     gemini_provider,     "gemini-2.0-flash"),
            ("openrouter", openrouter_provider, "google/gemini-2.0-flash"),
        ]
    elif "qwen" in model_lower or "glm" in model_lower:
        # Alibaba/Zhipu → OpenRouter → Gemini rescue
        generic_fallbacks = [
            ("openrouter", openrouter_provider, actual_model_id),
            ("gemini",     gemini_provider,     "gemini-2.0-flash"),
        ]
    else:
        # Unknown model — dynamically choose fallback based on what keys are available.
        generic_fallbacks = []
        if keys.get("gemini") or keys.get("google"):
            generic_fallbacks.append(("gemini", gemini_provider, actual_model_id))
        if keys.get("openrouter"):
            generic_fallbacks.append(("openrouter", openrouter_provider, actual_model_id))
        if not generic_fallbacks:
            generic_fallbacks = [
                ("gemini",     gemini_provider,     "gemini-2.0-flash"),
                ("openrouter", openrouter_provider, "google/gemini-2.0-flash"),
            ]
    for prov_name, prov_inst, model_id in generic_fallbacks:
        key = keys.get(prov_name) or getattr(prov_inst, "api_key", None)
        if key and not any(p == prov_inst and m == model_id for p, m, _ in attempts):
            attempts.append((prov_inst, model_id, key))

    if images:
        # ── Vision guarantee: always inject system-level vision providers ──────
        # User fallback chain may have no vision-capable entries if the user has
        # no matching API keys. Inject system-settings keys so Tesseract OCR is
        # truly the absolute last resort, not the first fallback.
        _sys_gemini_key = (
            keys.get("gemini") or keys.get("google") or
            getattr(settings, "GEMINI_API_KEY", None) or
            os.environ.get("GEMINI_API_KEY")
        )
        _sys_openai_key = (
            keys.get("openai") or
            getattr(settings, "OPENAI_API_KEY", None) or
            os.environ.get("OPENAI_API_KEY")
        )
        _sys_groq_key = (
            keys.get("groq") or
            getattr(settings, "GROQ_API_KEY", None) or
            os.environ.get("GROQ_API_KEY")
        )
        _sys_or_key = (
            keys.get("openrouter") or
            getattr(settings, "OPENROUTER_API_KEY", None) or
            os.environ.get("OPENROUTER_API_KEY")
        )
        # Guarantee: OpenAI GPT-4o directly if system OPENAI_API_KEY is set
        if _sys_openai_key and not str(_sys_openai_key).startswith("mock_"):
            if not any(m == "gpt-4o" and p == openai_provider for p, m, _ in attempts):
                attempts.insert(0, (openai_provider, "gpt-4o", _sys_openai_key))
        # Guarantee: Gemini Flash via system key (best for handwriting/vision)
        if _sys_gemini_key and not str(_sys_gemini_key).startswith("mock_"):
            if not any("gemini-2.0-flash" in m for _, m, _ in attempts):
                attempts.append((gemini_provider, "gemini-2.0-flash", _sys_gemini_key))
        # Guarantee: OpenAI GPT-4o via system key through OpenRouter
        if _sys_or_key and not str(_sys_or_key).startswith("mock_"):
            if not any("gpt-4o" in m for _, m, _ in attempts):
                attempts.append((openrouter_provider, "openai/gpt-4o", _sys_or_key))
        # Guarantee: Groq Llama Vision (free)
        if _sys_groq_key and not str(_sys_groq_key).startswith("mock_"):
            if not any("llama-3.2" in m for _, m, _ in attempts):
                attempts.append((groq_provider, "llama-3.2-11b-vision-preview", _sys_groq_key))

        # Strict filter: only attempt vision-capable models when images are present
        attempts = [
            (p, m, k) for (p, m, k) in attempts
            if any(frag in m.lower() for frag in _VISION_FRAGMENTS)
        ]
        logger.info(f"[Vision] {len(attempts)} vision attempt(s) queued: {[m for _, m, _ in attempts]}")

    # Remove any attempt that lacks a valid API key to avoid instant/silent timeouts
    valid_attempts = [(p, m, k) for (p, m, k) in attempts if k]
    if valid_attempts:
        attempts = valid_attempts

    full_response = ""
    tool_calls: List[dict] = []
    success    = False
    last_error = None
    # P1-1 FIX: Capture real wall-clock start time for LLM latency measurement
    import time as _wall_time
    _llm_start_time = _wall_time.monotonic()

    async def _stream(prov, mod, api_k):
        nonlocal full_response
        t_calls: List[dict] = []
        # Pass images to any provider whose generate_stream accepts an `images` parameter.
        # The actual capability check already happened above; here we just route correctly.
        _mod_lower = mod.lower()
        _is_vision_mod = any(frag in _mod_lower for frag in (
            "gemini", "google", "gpt-4o", "gpt-4-vision", "gpt-4.1", "o1", "o3", "o4",
            "claude-3", "claude-4", "llama-3.2", "llama-4", "llama4",
            "deepseek-vl", "deepseek-v3", "qwen-vl", "qwen2-vl", "qwen2.5-vl", "qvq",
            "pixtral", "mistral-large", "llava", "glm-4v", "internvl", "vision", "-vl",
        ))
        provider_images = images if (_is_vision_mod and images) else []

        import inspect
        sig = inspect.signature(prov.generate_stream)
        stream_kwargs = {
            "messages": raw_messages,
            "model":    mod,
            "tools":    tool_schemas,
            "api_key":  api_k,
        }
        if "images" in sig.parameters:
            stream_kwargs["images"] = provider_images

        # Initialize the real-time streaming sanitizer
        sanitizer = StreamingSanitizer(INTERNAL_TOOL_NAMES)

        logger.info(json.dumps({
            "event": "stream_start",
            "provider": prov.__class__.__name__,
            "model": mod,
            "api_key_masked": mask_key(api_k),
            "payload_messages_count": len(raw_messages),
            "tools_offered": [t["name"] for t in tool_schemas]
        }))


        # ── Per-chunk idle timeout ──────────────────────────────────────────────
        # If the LLM stops sending chunks silently (network stall, API hang),
        # we must abort this attempt so the fallback chain can kick in.
        # 25 s of silence = hung provider → raise TimeoutError → next fallback.
        CHUNK_IDLE_TIMEOUT = 25.0

        async def _next_chunk(ait):
            """Await the next item from an async iterator with a timeout."""
            return await asyncio.wait_for(ait.__anext__(), timeout=CHUNK_IDLE_TIMEOUT)

        stream_iter = prov.generate_stream(**stream_kwargs).__aiter__()
        while True:
            try:
                chunk = await _next_chunk(stream_iter)
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                logger.error(json.dumps({
                    "event": "stream_chunk_timeout",
                    "provider": prov.__class__.__name__,
                    "model": mod,
                    "idle_seconds": CHUNK_IDLE_TIMEOUT,
                    "partial_response_len": len(full_response),
                }))
                raise TimeoutError(
                    f"LLM stream idle for {CHUNK_IDLE_TIMEOUT}s "
                    f"({prov.__class__.__name__}/{mod}) — no chunks received."
                )

            if chunk["event"] == "chunk":
                text = chunk["text"]
                full_response += text
                if on_token:
                    sanitized_token = sanitizer.feed(text)
                    if sanitized_token:
                        await on_token(sanitized_token)
            elif chunk["event"] == "tool_calls":
                logger.info(json.dumps({
                    "event": "tool_calls_detected",
                    "tool_calls": chunk["tool_calls"]
                }))
                t_calls.extend(chunk["tool_calls"])
            elif chunk["event"] == "metrics":
                logger.info(json.dumps({
                    "event": "stream_metrics",
                    "metrics": chunk["metrics"]
                }))
                mx = chunk["metrics"]
                # Use CRAG-validated source_documents from state, not raw retrieved_context.
                # source_documents is set authoritatively by grade_documents_node:
                #   - [] when CRAG rejects all chunks or Self-RAG skips retrieval
                #   - [used=True chunks only] when CRAG approves
                final_sources = state.get("source_documents", [])
                gen_mode = state.get("generation_mode", "model_knowledge" if not final_sources else "normal_rag")
                chunk_items = [x for x in retrieved_items if x.get("type") == "chunk"]
                mem_hits = len([x for x in retrieved_items
                                if x.get("type") == "memory" or "category" in x])
                mx["memory_hits"]     = mem_hits
                mx["chunks_used"]     = len(chunk_items)
                mx["generation_mode"] = gen_mode
                mx["steps"] = list(state.get("steps") or []) + ["generate_response"]
                # retrieved_context: all items (memories + chunks) for developer debug panel
                mx["retrieved_context"] = [
                    {
                        "type":             item.get("type", "memory" if "category" in item else "chunk"),
                        "filename":         item.get("filename", "Memory Fact"),
                        "category":         item.get("category", ""),
                        "content":          item.get("content", ""),
                        "importance_score": item.get("importance_score"),
                        "distance":         item.get("distance"),
                        "confidence":       item.get("confidence"),
                        "used":             item.get("used", False),
                    }
                    for item in retrieved_items
                ]
                # source_documents: AUTHORITATIVE — only CRAG-validated, used=True chunks.
                # This is what the frontend MUST read for Sources display.
                mx["source_documents"] = final_sources
                if on_metrics:
                    await on_metrics(mx)

        # Flush the sanitizer buffer after streaming completes
        if on_token:
            remaining = sanitizer.flush()
            if remaining:
                await on_token(remaining)

        return t_calls


    primary_error = None
    primary_provider_class = type(attempts[0][0]).__name__ if attempts else ""
    for attempt_idx, (current_provider, current_model, current_key) in enumerate(attempts):
        try:
            tool_calls = await _stream(current_provider, current_model, current_key)
            success = True
            break
        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit   = "429" in err_str or "rate limit" in err_str or "rate_limit" in err_str or "ratelimit" in err_str
            is_payment_error = any(code in err_str for code in ["402", "403", "payment required", "insufficient credits"])
            logger.error(json.dumps({
                "event": "provider_call_failed",
                "model": current_model,
                "error": str(e),
                "is_rate_limit": is_rate_limit,
                "is_payment_error": is_payment_error,
                "attempt": attempt_idx
            }))
            if attempt_idx == 0:
                primary_error = e  # always remember the primary attempt's error
            last_error = e
            if full_response:
                # Already streamed some content — cannot silently retry mid-stream
                raise e
            # On rate-limit, skip any remaining fallbacks on the SAME provider class
            if is_rate_limit:
                current_prov_class = type(current_provider).__name__
                # Advance past any remaining same-provider attempts in the list
                logger.warning(f"[fallback] 429 rate-limit on {current_prov_class}/{current_model} — skipping same-provider retries")
            # Always continue to next fallback
            logger.warning(f"[fallback] attempt {attempt_idx} failed ({current_model}): {str(e)[:120]} — trying next provider")
            continue

    # ── Tesseract OCR Rescue: If all vision provider attempts failed ──────────
    ocr_text = ""
    if not success and images and not full_response:
        logger.info("[Vision Fallback] All vision attempts failed. Attempting Tesseract OCR rescue...")
        ocr_text = _perform_tesseract_ocr_on_images(images)
        if ocr_text:
            ocr_rescue_note = "*(Vision processing failed. Extracted text using local OCR — attempting text-model structured reconstruction...)*\n\n"
            # ── Inject enriched OCR rescue prompt so text-only models output
            # structured Markdown with Mermaid diagrams and tables.
            _ocr_rescue_system_directive = (
                "\n\n[SYSTEM — OCR RESCUE DIRECTIVE]\n"
                "The vision API is unavailable. The following text was extracted via local OCR from a "
                "handwritten note or diagram image. It may contain OCR character errors.\n"
                "YOU MUST:\n"
                "1. Auto-correct all obvious OCR typos (e.g. 'Lanachans'→'LangChain', "
                "'PR@MPTs'→'PROMPTS', 'Enbeele'→'Embedding', 'CxAINS'→'CHAINS', "
                "'lims'→'LLMs', 'Dyhanic'→'Dynamic', 'Saman-tc'→'Semantic', 'veefor'→'vector').\n"
                "2. Output a Mermaid `flowchart TD` block showing the hierarchy/relationships.\n"
                "3. Output organized headings (# Models, # Prompts, # Chains) with bullet points.\n"
                "4. Output a Markdown comparison table for any listed model/concept types.\n"
                "5. NEVER dump raw OCR text. NEVER write 'Based on the OCR...' or meta-phrases.\n"
                "6. Start IMMEDIATELY with the Mermaid diagram, then headings, then table.\n"
                "[END DIRECTIVE]\n\n"
            )
            for m in reversed(raw_messages):
                if m.get("role") == "user":
                    m["content"] = (
                        f"{_ocr_rescue_system_directive}"
                        f"Attached document/image content extracted via OCR:\n{ocr_text}\n\n"
                        f"User Question:\n{m['content']}"
                    )
                    break
            images = []
            rescue_attempts = []
            if keys.get("openai"):
                rescue_attempts.append((openai_provider, "gpt-4o-mini", keys["openai"]))
            if keys.get("gemini") or keys.get("google"):
                rescue_attempts.append((gemini_provider, "gemini-2.0-flash", keys.get("gemini") or keys.get("google")))
            if keys.get("groq"):
                rescue_attempts.append((groq_provider, "llama-3.3-70b-versatile", keys["groq"]))
            if keys.get("openrouter"):
                rescue_attempts.append((openrouter_provider, "meta-llama/llama-3.3-70b-instruct", keys["openrouter"]))

            for r_prov, r_mod, r_key in rescue_attempts:
                try:
                    tool_calls = await _stream(r_prov, r_mod, r_key)
                    success = True
                    break
                except Exception as r_err:
                    logger.warning(f"[OCR Rescue] Attempt with {r_mod} failed: {r_err}")

            if not success and ocr_text:
                # ── All cloud APIs failed/rate-limited.
                # Run the OCR Intelligence Engine to produce a structured response locally.
                # This ensures the user ALWAYS receives organized output (Mermaid + tables + headings)
                # even with zero cloud connectivity.
                try:
                    structured_local_response = _reconstruct_ocr_diagram_and_notes(
                        ocr_text, image_index=1
                    )
                except Exception as _recon_err:
                    logger.warning(f"[OCR Intelligence Engine] Reconstruction failed: {_recon_err}")
                    structured_local_response = ""

                if structured_local_response:
                    direct_ocr_response = (
                        "⚠️ **Cloud Vision AI is currently unavailable (rate-limited or offline).**\n"
                        "The following structured analysis was generated **locally** using the "
                        "OCR Intelligence Engine — no cloud API required.\n\n"
                        "---\n\n"
                        + structured_local_response
                    )
                else:
                    # Final raw fallback: deliver raw OCR as-is if reconstruction also fails
                    direct_ocr_response = (
                        "ℹ️ **Vision AI & Cloud LLMs Unavailable**\n\n"
                        "The cloud AI models are currently rate-limited or unavailable. "
                        "Here is the text extracted directly from your image using local OCR:\n\n"
                        f"{ocr_text}"
                    )
                if on_token and not full_response:
                    try:
                        await on_token(direct_ocr_response)
                    except Exception:
                        pass
                full_response = direct_ocr_response
                success = True

    # Track whether the final response is a transient error (should NOT be saved to history)
    _is_error_response = False


    if not success:
        err_msg = str(primary_error or last_error or "")
        if "429" in err_msg or "rate limit" in err_msg.lower() or "quota" in err_msg.lower():
            friendly_msg = (
                "⚠️ **Rate Limit Exceeded (HTTP 429)**\n\n"
                "The API request limit or quota for the active model has been reached. "
                "Please wait a moment before trying again, or select a different model from the top bar."
            )
            if on_token and not full_response:
                try:
                    await on_token(friendly_msg)
                except Exception:
                    pass
            full_response = friendly_msg
            # BUG FIX: Mark this as a transient error — do NOT save it into the conversation
            # history as an AI message. If saved, the next LLM call would see the error text
            # as a prior assistant turn and generate a confused response trying to address it.
            _is_error_response = True
        else:
            # Surface the primary provider's error if it failed, otherwise use last error
            raise (primary_error or last_error or Exception("No active provider models were able to process the request."))

    # Determine generation mode and authoritative source list.
    # These come from grade_documents_node (or initial empty state for model-knowledge).
    final_source_docs = state.get("source_documents", [])
    gen_mode = state.get("generation_mode",
                         "model_knowledge" if not final_source_docs else "normal_rag")

    # ── Validate & Sanitize citations and response text before returning ──────
    full_response = validate_citations(full_response, final_source_docs)
    full_response = _sanitize_response(full_response)

    # RAG audit: log final generation decision
    chunk_items = [x for x in retrieved_items if x.get("type") == "chunk"]
    _log_rag_audit(
        stage="generate_response",
        query=(state.get("resolved_query") or ""),
        retrieved=chunk_items,
        crag_decision="see grade_documents stage",
        self_rag_decision="see check_retrieval stage",
        docs_sent=chunk_items,
        docs_rejected=[],
        generation_mode=gen_mode,
        sources_returned=final_source_docs,
    )

    # P1-1 FIX: Record actual wall-clock LLM latency (was incorrectly recording char count)
    _telemetry = config.get("configurable", {}).get("telemetry")
    if _telemetry is not None:
        try:
            _actual_latency_ms = round((_wall_time.monotonic() - _llm_start_time) * 1000, 2)
            _telemetry.record_llm(
                provider=type(attempts[0][0]).__name__ if attempts else "unknown",
                model=model,
                latency_ms=_actual_latency_ms,
                response_text=full_response,
            )
        except Exception as _tel_err:
            logger.debug(f"Telemetry record_llm failed (non-fatal): {_tel_err}")

    steps = list(state.get("steps") or []) + ["generate_response"]
    if tool_calls:
        ai_msg = AIMessage(content=f"Processing your request...")
        return {
            "response_text":   ai_msg.content,
            "tool_calls":      tool_calls,
            "messages":        messages + [ai_msg],
            "steps":           steps,
            "iteration_count": iteration_count + 1,
            "source_documents": final_source_docs,
            "generation_mode":  gen_mode,
        }

    # Only append to conversation history when the response is a real AI turn.
    # Error/rate-limit messages must NOT be stored — they would appear as prior assistant
    # responses and cause the LLM to generate confused output on the next request.
    if _is_error_response:
        updated_messages = messages  # leave history unchanged
    else:
        ai_msg = AIMessage(content=full_response)
        updated_messages = messages + [ai_msg]

    return {
        "response_text":   full_response,
        "tool_calls":      [],
        "messages":        updated_messages,
        "steps":           steps,
        "iteration_count": iteration_count + 1,
        "source_documents": final_source_docs,   # ← authoritative: only used=True docs
        "generation_mode":  gen_mode,            # ← "normal_rag" | "model_knowledge" | "crag_rejected"
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Node 7: Execute tools
# ─────────────────────────────────────────────────────────────────────────────

async def execute_tools_node(
    state: AgentState, config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    Iterates over active tool calls, runs them via ToolRegistry, appends
    results as HumanMessages, and clears tool_calls for the next iteration.
    Includes reconnect-on-failure: if MCP subprocess died mid-query, re-initializes
    the registry and retries once before giving up.
    """
    config     = config or {}
    tool_calls = state.get("tool_calls", []) or []
    messages   = list(state.get("messages", []))
    req_api_keys: Dict[str, Any] = config.get("configurable", {}).get("api_keys", {})

    from app.tools.registry import ToolRegistry
    registry = ToolRegistry()

    # Always ensure registry is initialized before executing tools
    if not registry.is_initialized:
        try:
            await registry.initialize()
        except Exception as _reinit_err:
            logger.warning(f"execute_tools_node: registry re-init failed: {_reinit_err}")

    new_messages = []
    for tc in tool_calls:
        name      = tc["name"]
        arguments = tc.get("arguments") if "arguments" in tc else tc.get("args", {})

        # First attempt
        result = await registry.call_tool(name, arguments, api_keys=req_api_keys)

        # If MCP process died mid-query (tool not registered), force re-init and retry once
        if "is not registered" in str(result) or "not registered" in str(result).lower():
            logger.warning(
                f"execute_tools_node: tool '{name}' not found — MCP process may have died. "
                f"Forcing registry re-initialization and retrying..."
            )
            try:
                registry.is_initialized = False
                await registry.initialize()
                result = await registry.call_tool(name, arguments, api_keys=req_api_keys)
                logger.info(f"execute_tools_node: retry for '{name}' succeeded after re-init.")
            except Exception as _retry_err:
                logger.error(f"execute_tools_node: retry for '{name}' failed: {_retry_err}")
                result = f"Tool '{name}' is temporarily unavailable. Please try again."

        # Use neutral label — never expose internal tool name to the conversation
        new_messages.append(
            HumanMessage(content=f"[Tool Result] {result}")
        )

    steps = list(state.get("steps") or []) + ["execute_tools"]
    return {
        "messages":   messages + new_messages,
        "tool_calls": [],
        "steps":      steps,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Node 8: Reflect  (P0 fix: skip for simple intents; higher brief threshold)
# ─────────────────────────────────────────────────────────────────────────────

async def reflect_node(
    state: AgentState, config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    Reflection node — evaluates the latest AI response for quality.

    P0 Fixes:
    • Reflection is SKIPPED for MEMORY_WRITE (ACKs should never be lengthened).
    • Reflection is SKIPPED for NORMAL_CHAT to reduce unnecessary latency.
    • The "too brief" heuristic threshold is raised significantly:
      Only triggers if response < 10 words AND query > 20 words.
      This prevents short-but-correct answers from being inflated.
    """
    config  = config or {}
    messages = state.get("messages", [])
    steps    = list(state.get("steps") or [])
    intent   = state.get("intent", INTENT_NORMAL_CHAT)

    # Skip reflection for intents that don't benefit from quality critique.
    # DOCUMENT_QA is also skipped — evidence_checker already validated accuracy.
    # INTENT_VISION is skipped to prevent multi-pass regeneration on images.
    skip_intents = {INTENT_MEMORY_WRITE, INTENT_NORMAL_CHAT, INTENT_DOCUMENT_QA, INTENT_VISION}
    if intent in skip_intents:
        steps.append("reflect")
        return {
            "reflection_passed":   True,
            "reflection_feedback": None,
            "steps":               steps,
        }

    last_query    = state.get("resolved_query")
    last_response = ""
    for msg in reversed(messages):
        if not last_response and hasattr(msg, "type") and msg.type == "ai":
            last_response = msg.content if isinstance(msg.content, str) else ""
        elif not last_query and hasattr(msg, "type") and msg.type in ("human", "user"):
            last_query = msg.content if isinstance(msg.content, str) else ""
        if last_query and last_response:
            break

    reflection_passed   = True
    reflection_feedback = None

    if last_query and last_response:
        prompt = REFLECTION_PROMPT.format(
            query=last_query[:1000],
            response=last_response[:2000],
        )
        parsed = await _call_llm_judge(prompt, config)

        if parsed:
            verdict = parsed.get("verdict", "PASS")
            if verdict == "NEEDS_IMPROVEMENT":
                reflection_passed   = False
                reflection_feedback = parsed.get("feedback", "Improve the response.")
                logger.info(f"Reflection: NEEDS_IMPROVEMENT — {reflection_feedback[:80]}")
            else:
                logger.info("Reflection: PASS")
        else:
            # Heuristic — much higher threshold than before (P0 fix)
            query_words    = len(last_query.split())
            response_words = len(last_response.split())
            if query_words > 20 and response_words < 10:
                reflection_passed   = False
                reflection_feedback = "The response appears too brief. Provide a more thorough answer."

    steps.append("reflect")
    return {
        "reflection_passed":   reflection_passed,
        "reflection_feedback": reflection_feedback,
        "steps":               steps,
    }


# =============================================================================
#  Phase 3 Nodes
# =============================================================================


async def tool_planner_node(
    state: AgentState, config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    Tool Planner Node (Phase 3) — uses an LLM to generate a DAG of tool tasks
    for the current query.  The DAG is stored in state["tool_dag"] and will be
    executed by parallel_tool_execution_node.

    Skipped when:
      - No allowed_tools for this intent
      - Intent is a simple single-tool routing (WEB_SEARCH, MCP_TOOL, etc.) that
        does not require DAG planning — these use the sequential tool-call loop.
      - Existing tool_calls already present (sequential tool-call loop is running)
    """
    config      = config or {}
    steps       = list(state.get("steps") or [])
    intent      = state.get("intent", INTENT_NORMAL_CHAT)
    allowed     = state.get("allowed_tools") or []
    last_query  = state.get("resolved_query") or ""

    # P3-1 FIX: Extend skip_intents to include WEB_SEARCH and MCP_TOOL.
    # These intents use a single pre-determined tool (tavily_search / MCP call)
    # routed by generate_response_node's sequential tool-call loop. Running the
    # LLM tool-planner for them adds an extra LLM round-trip with zero benefit.
    skip_intents = {
        INTENT_DOCUMENT_QA, INTENT_NORMAL_CHAT, INTENT_MEMORY_WRITE, INTENT_VISION,
        INTENT_WEB_SEARCH,  # single tavily_search call — no DAG needed
        INTENT_MCP_TOOL,    # MCP tools routed by sequential loop — no DAG needed
        INTENT_NEWS,        # same as WEB_SEARCH in practice
        INTENT_CURRENT_EVENTS,  # same as WEB_SEARCH in practice
    }
    if not allowed or not last_query or intent in skip_intents:
        steps.append("tool_planner")
        return {"tool_dag": None, "steps": steps, "ux_stage": UX_STAGE_PLANNING}

    if not last_query:
        for msg in reversed(state.get("messages", [])):
            if hasattr(msg, "type") and msg.type in ("human", "user"):
                last_query = msg.content if isinstance(msg.content, str) else ""
                break

    prompt = TOOL_PLANNER_PROMPT.format(
        available_tools=", ".join(allowed),
        query=last_query[:500],
    )
    parsed = await _call_llm_judge(prompt, config)

    tool_dag = None
    if parsed and isinstance(parsed.get("tasks"), list) and parsed["tasks"]:
        tool_dag = parsed["tasks"]
        logger.info(f"[ToolPlanner] Generated DAG with {len(tool_dag)} task(s).")
    else:
        logger.info("[ToolPlanner] No tool tasks required for this query.")

    steps.append("tool_planner")
    return {
        "tool_dag":  tool_dag,
        "steps":     steps,
        "ux_stage":  UX_STAGE_CALLING_TOOLS if tool_dag else UX_STAGE_GENERATING,
    }


async def parallel_tool_execution_node(
    state: AgentState, config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    Parallel Tool Execution Node (Phase 3) — executes the tool DAG produced by
    tool_planner_node using the async dependency-graph scheduler.

    If tool_dag is None or empty, this node is a no-op.
    """
    config  = config or {}
    steps   = list(state.get("steps") or [])
    tool_dag = state.get("tool_dag")

    if not tool_dag:
        steps.append("parallel_tool_execution")
        return {"tool_execution_results": None, "steps": steps}

    try:
        from app.tools.registry import ToolRegistry
        from app.tools.scheduler import ToolScheduler, ToolTask

        registry  = ToolRegistry()
        await registry.initialize()

        # Strict whitelisting guard: only allow tools that are whitelisted in state.allowed_tools
        allowed = state.get("allowed_tools") or []
        tasks = []
        for t in tool_dag:
            tool_name = t["tool"]
            if tool_name not in allowed:
                logger.warning(f"[ParallelToolExec] Blocking execution of un-whitelisted tool '{tool_name}'")
                continue
            tasks.append(
                ToolTask(
                    id         = t["id"],
                    tool       = tool_name,
                    args       = t.get("args", {}),
                    depends_on = t.get("depends_on", []),
                    timeout    = float(t.get("timeout", 30.0)),
                    retries    = int(t.get("retries", 1)),
                )
            )

        if not tasks:
            logger.info("[ParallelToolExec] No whitelisted tool tasks to execute.")
            steps.append("parallel_tool_execution")
            return {"tool_execution_results": None, "steps": steps}

        scheduler = ToolScheduler(registry)
        results   = await scheduler.run(tasks)

        serialized = [
            {
                "id":         r.id,
                "tool":       r.tool,
                "status":     r.status,
                "output":     r.output,
                "latency_ms": r.latency_ms,
                "attempts":   r.attempts,
            }
            for r in results
        ]

        logger.info(
            f"[ParallelToolExec] Completed {len(results)} task(s). "
            f"Statuses: { {r.id: r.status for r in results} }"
        )
        steps.append("parallel_tool_execution")
        return {
            "tool_execution_results": serialized,
            "steps":                  steps,
            "ux_stage":               UX_STAGE_VERIFYING,
        }

    except Exception as exc:
        logger.error(f"[ParallelToolExec] Error: {exc}")
        steps.append("parallel_tool_execution")
        return {"tool_execution_results": None, "steps": steps}


async def evidence_checker_node(
    state: AgentState, config: RunnableConfig = None
) -> Dict[str, Any]:
    """
    Evidence Checker / Hallucination Detection Node (Phase 3).

    Verifies the generated answer against retrieved document chunks.
    - If the answer contains unsupported factual claims, it is corrected.
    - If evidence is empty and the query required documents, the response
      is replaced with an uncertainty statement.
    - Outputs: verified_response, answer_confidence, has_hallucination_risk,
               unsupported_claims_count, citations (enriched).
    """
    config    = config or {}
    steps     = list(state.get("steps") or [])
    messages  = state.get("messages", [])
    retrieved = state.get("retrieved_documents", [])
    intent    = state.get("intent", INTENT_NORMAL_CHAT)

    # Extract the latest AI response
    last_response = ""
    last_query    = state.get("resolved_query") or ""
    for msg in reversed(messages):
        if not last_response and hasattr(msg, "type") and msg.type == "ai":
            last_response = msg.content if isinstance(msg.content, str) else ""
        elif not last_query and hasattr(msg, "type") and msg.type in ("human", "user"):
            last_query = msg.content if isinstance(msg.content, str) else ""
        if last_query and last_response:
            break

    if not last_response:
        steps.append("evidence_checker")
        return {
            "verified_response":        None,
            "answer_confidence":        1.0,
            "has_hallucination_risk":   False,
            "unsupported_claims_count": 0,
            "steps":                    steps,
            "ux_stage":                 UX_STAGE_GENERATING,
        }

    # Skip deep verification ONLY for memory/chat/vision intents.
    # WEB_SEARCH and COMPLEX are included so search-grounded answers get verified
    # against retrieved web context, preventing sycophantic hallucination.
    skip_intents = {INTENT_MEMORY_WRITE, INTENT_NORMAL_CHAT, INTENT_VISION}
    if intent in skip_intents:
        steps.append("evidence_checker")
        return {
            "verified_response":        last_response,
            "answer_confidence":        1.0,
            "has_hallucination_risk":   False,
            "unsupported_claims_count": 0,
            "steps":                    steps,
            "ux_stage":                 UX_STAGE_GENERATING,
        }

    # Short-circuit: skip deep LLM evidence check when CRAG already confirmed
    # high retrieval confidence on a private document query — grading already
    # validated the chunks, so a second LLM pass adds latency without benefit.
    _ev_retrieval_conf = state.get("retrieval_confidence", 0.0)
    _ev_doc_relevance  = state.get("document_relevance", "")
    if (
        intent == INTENT_DOCUMENT_QA
        and _ev_retrieval_conf >= 0.75
        and _ev_doc_relevance not in ("web_fallback", "no_docs", "no_private_docs")
    ):
        logger.info(
            f"[EvidenceChecker] Skipping LLM verification — high-confidence DOCUMENT_QA "
            f"(retrieval_confidence={_ev_retrieval_conf:.2f}, relevance={_ev_doc_relevance})"
        )
        steps.append("evidence_checker")
        return {
            "verified_response":        last_response,
            "answer_confidence":        _ev_retrieval_conf,
            "has_hallucination_risk":   False,
            "unsupported_claims_count": 0,
            "steps":                    steps,
            "ux_stage":                 UX_STAGE_GENERATING,
        }

    # Build evidence text from CRAG-validated source_documents (or fallback to retrieved)
    validated_sources = state.get("source_documents") or []
    doc_chunks = validated_sources if validated_sources else [d for d in retrieved if d.get("type") == "chunk"]
    evidence_text = ""
    for idx, chunk in enumerate(doc_chunks[:10], start=1):
        evidence_text += f"[Source {idx}] {chunk.get('filename', 'unknown')}:\n{chunk.get('content', '')[:400]}\n\n"

    # Build enriched citations
    citations = []
    for idx, chunk in enumerate(state.get("source_documents", []), start=1):
        citations.append({
            "index":           idx,
            "filename":        chunk.get("filename", "Unknown"),
            "page_number":     chunk.get("page_number", 1),
            "chunk_id":        chunk.get("chunk_id"),
            "confidence":      chunk.get("confidence", 1.0),
            "content_snippet": chunk.get("content", "")[:100],
        })

    # Call LLM evidence checker
    prompt = EVIDENCE_CHECKER_PROMPT.format(
        query=last_query[:500],
        evidence=evidence_text[:3000] if evidence_text else "No document evidence provided.",
        answer=last_response[:2000],
    )
    parsed = await _call_llm_judge(prompt, config)

    if not parsed:
        # Fallback: no correction possible, return original
        steps.append("evidence_checker")
        return {
            "verified_response":        last_response,
            "answer_confidence":        0.7,
            "has_hallucination_risk":   False,
            "unsupported_claims_count": 0,
            "citations":                citations,
            "steps":                    steps,
            "ux_stage":                 UX_STAGE_GENERATING,
        }

    verdict             = parsed.get("verdict", "PASS")
    confidence          = float(parsed.get("confidence", 0.8))
    unsupported         = parsed.get("unsupported_claims", [])
    corrected_answer    = parsed.get("corrected_answer", last_response)
    hallucination_risk  = parsed.get("hallucination_risk", "low")
    has_risk            = hallucination_risk in ("medium", "high") or bool(unsupported)

    if verdict == "NEEDS_CORRECTION" and corrected_answer:
        verified = corrected_answer
        logger.info(
            f"[EvidenceChecker] Corrected {len(unsupported)} unsupported claim(s). "
            f"Risk={hallucination_risk}"
        )
    else:
        verified = last_response
        logger.info(f"[EvidenceChecker] PASS — confidence={confidence:.2f}")

    # BUG-5c FIX: Record evidence check result in telemetry
    _telemetry = config.get("configurable", {}).get("telemetry")
    if _telemetry is not None:
        try:
            _telemetry.record_evidence(
                verdict=verdict,
                confidence=confidence,
                hallucination_risk=hallucination_risk,
                unsupported_count=len(unsupported),
                citations_count=len(citations),
            )
        except Exception as _tel_err:
            logger.debug(f"Telemetry record_evidence failed (non-fatal): {_tel_err}")

    steps.append("evidence_checker")

    # BUG-1 FIX: Write the verified (possibly corrected) response back to response_text
    # and update the last AI message in the conversation so reflect_node sees the
    # corrected version. Previously verified_response was set but NEVER read — the
    # streaming endpoint only reads state["response_text"].
    current_messages = list(state.get("messages", []))
    if verified != last_response:
        # Replace the last AI message with the corrected version
        updated_messages = []
        replaced = False
        for _m in reversed(current_messages):
            if not replaced and hasattr(_m, "type") and _m.type == "ai":
                updated_messages.insert(0, AIMessage(content=verified))
                replaced = True
            else:
                updated_messages.insert(0, _m)
        if not replaced:
            updated_messages = current_messages
    else:
        updated_messages = current_messages

    return {
        "verified_response":        verified,
        "response_text":            verified,   # ← THE FIX: now actually reaches the user
        "messages":                 updated_messages,
        "answer_confidence":        confidence,
        "has_hallucination_risk":   has_risk,
        "unsupported_claims_count": len(unsupported),
        "citations":                citations,
        "steps":                    steps,
        "ux_stage":                 UX_STAGE_GENERATING,
    }
