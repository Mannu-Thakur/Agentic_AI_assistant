"""
tools/advanced_tools.py — Advanced agent tools for translation, summarization,
SQL database queries, document search, and long-context analysis.

All functions follow the established pattern:
  async def tool_name(param: str, ...) -> str
  • Never raise — always return an error string on failure.
  • Return formatted markdown strings ready for LLM consumption.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Internal LLM helper — smart fallback chain mirroring nodes.py
# ─────────────────────────────────────────────────────────────────────────────

class _LLMResult:
    """Lightweight result container returned by _llm_complete."""
    __slots__ = ("content", "provider", "model", "fallback_used", "error")

    def __init__(self, content=None, provider=None, model=None, fallback_used=False, error=None):
        self.content = content
        self.provider = provider
        self.model = model
        self.fallback_used = fallback_used
        self.error = error

    @property
    def ok(self) -> bool:
        return bool(self.content)


# Errors that justify trying the next provider in the chain.
# Anything else (bad key, bad model ID, empty body) is a permanent/config
# error — do not cascade, return cleanly to the caller.
_FALLBACK_EXCEPTIONS: tuple = ()   # populated lazily below


def _get_fallback_exceptions() -> tuple:
    """Lazily import & cache the provider exception classes that warrant fallback."""
    global _FALLBACK_EXCEPTIONS
    if _FALLBACK_EXCEPTIONS:
        return _FALLBACK_EXCEPTIONS
    try:
        from app.providers.openai_provider import (
            ProviderRateLimitError,
            ProviderServerError,
            ProviderTimeoutError,
            ProviderCircuitOpenError,
        )
        _FALLBACK_EXCEPTIONS = (
            ProviderRateLimitError,   # 429 — quota/rate limit → next provider
            ProviderServerError,      # 5xx — provider down → next provider
            ProviderTimeoutError,     # network timeout → next provider
            ProviderCircuitOpenError, # circuit breaker tripped → next provider
        )
    except ImportError:
        # If we can't import the specific exceptions, fall back on keyword matching
        _FALLBACK_EXCEPTIONS = ()
    return _FALLBACK_EXCEPTIONS


def _should_fallback(exc: Exception) -> bool:
    """
    Return True only when the exception signals a TRANSIENT or CAPACITY issue
    (rate limit, server error, timeout, circuit open) — i.e. trying another
    provider is worth attempting.

    Return False for PERMANENT errors (bad API key, invalid model, bad request,
    empty response) — cascading would just waste time and confuse the user.
    """
    fallback_types = _get_fallback_exceptions()
    if fallback_types and isinstance(exc, fallback_types):
        return True

    # Keyword-based fallback for when exception classes can't be imported
    msg = str(exc).lower()
    transient_keywords = (
        "rate limit", "rate_limit", "too many requests", "429",
        "server error", "503", "502", "504", "500",
        "timed out", "timeout", "connection",
        "circuit", "temporarily",
        "quota", "insufficient_quota", "tokens per",
    )
    permanent_keywords = (
        "401", "unauthorized", "invalid api key", "api key",
        "invalid_api_key", "authentication",
        "400", "bad request", "model unavailable", "model_not_found",
        "does not exist", "empty response",
    )
    for kw in permanent_keywords:
        if kw in msg:
            return False
    for kw in transient_keywords:
        if kw in msg:
            return True
    # Unknown error — do NOT fall back; log and stop
    return False


async def _llm_complete(prompt: str, max_tokens: int = 1024) -> _LLMResult:
    """
    Call the best available LLM provider with a single user prompt.

    Fallback chain: Gemini → OpenAI → Groq → OpenRouter

    Fallback rules (STRICT):
    ─ DO fall back on:  rate limit (429) · server error (5xx) · timeout · circuit open
    ─ DO NOT fall back: bad key (401) · bad model (400/404) · empty response · unknown errors

    Returns an _LLMResult with:
      .content     — the LLM response text (None on failure)
      .provider    — name of provider that succeeded
      .model       — model name used
      .fallback_used — True if we had to skip 1+ providers
      .error       — human-readable error description (if .ok is False)
    """
    import os
    from app.core.config import settings

    messages = [{"role": "user", "content": prompt}]
    skipped_providers: list[str] = []

    # ── Provider definitions ──────────────────────────────────────────────────
    # Each entry: (env_key_attr, provider_class_path, model_attr, default_model, label)
    provider_chain = [
        {
            "name": "Gemini",
            "key_attr": "GEMINI_API_KEY",
            "class_path": ("app.providers.gemini", "GeminiProvider"),
            "model_attr": "GEMINI_MODEL",
            "default_model": "gemini-3.5-flash",
        },
        {
            "name": "OpenAI",
            "key_attr": "OPENAI_API_KEY",
            "class_path": ("app.providers.openai_provider", "OpenAIProvider"),
            "model_attr": "OPENAI_MODEL",
            "default_model": "gpt-4o-mini",
        },
        {
            "name": "Groq",
            "key_attr": "GROQ_API_KEY",
            "class_path": ("app.providers.groq", "GroqProvider"),
            "model_attr": "GROQ_MODEL",
            "default_model": "llama-3.3-70b-versatile",
        },
        {
            "name": "OpenRouter",
            "key_attr": "OPENROUTER_API_KEY",
            "class_path": ("app.providers.openrouter", "OpenRouterProvider"),
            "model_attr": "OPENROUTER_MODEL",
            "default_model": "openrouter/auto",
        },
    ]

    last_transient_error: str | None = None

    for entry in provider_chain:
        # Skip if no API key configured
        key = (
            getattr(settings, entry["key_attr"], None)
            or os.environ.get(entry["key_attr"])
        )
        if not key or str(key).startswith("mock_"):
            logger.debug(f"[_llm_complete] {entry['name']} skipped — no API key.")
            continue

        model = (
            getattr(settings, entry["model_attr"], None)
            or entry["default_model"]
        )
        provider_label = entry["name"]

        try:
            import importlib
            mod = importlib.import_module(entry["class_path"][0])
            ProviderClass = getattr(mod, entry["class_path"][1])
            provider = ProviderClass()

            result = await provider.generate(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
            )
            content = result.get("content") or result.get("text") or ""
            if not content:
                # Provider returned 200 but empty body — don't cascade (not a
                # capacity issue), just log and treat as failure.
                logger.warning(
                    f"[_llm_complete] {provider_label} returned empty content "
                    f"(model={model}). Not falling back."
                )
                return _LLMResult(
                    error=(
                        f"The AI provider ({provider_label}) returned an empty response. "
                        "Please try again."
                    )
                )

            was_fallback = bool(skipped_providers)
            if was_fallback:
                logger.info(
                    f"[_llm_complete] Fallback succeeded via {provider_label} "
                    f"(model={model}) after skipping: {', '.join(skipped_providers)}"
                )
            else:
                logger.debug(f"[_llm_complete] {provider_label} succeeded (model={model}).")

            return _LLMResult(
                content=content.strip(),
                provider=provider_label,
                model=model,
                fallback_used=was_fallback,
            )

        except Exception as exc:
            if _should_fallback(exc):
                # Transient/capacity error — log at INFO and try next provider
                logger.info(
                    f"[_llm_complete] {provider_label} transient error "
                    f"({type(exc).__name__}: {str(exc)[:120]}) — "
                    f"falling back to next provider."
                )
                skipped_providers.append(provider_label)
                last_transient_error = (
                    f"{provider_label}: {type(exc).__name__} — {str(exc)[:120]}"
                )
                continue  # → try next provider
            else:
                # Permanent / config error — stop immediately
                logger.error(
                    f"[_llm_complete] {provider_label} permanent error "
                    f"({type(exc).__name__}: {str(exc)[:200]}). Stopping."
                )
                return _LLMResult(
                    error=(
                        f"The AI provider ({provider_label}) could not process this request: "
                        f"{str(exc)[:200]}"
                    )
                )

    # All providers exhausted
    if skipped_providers:
        logger.error(
            f"[_llm_complete] All providers exhausted after fallback. "
            f"Tried: {', '.join(skipped_providers)}. "
            f"Last error: {last_transient_error}"
        )
        return _LLMResult(
            error=(
                "All AI providers are currently unavailable (rate limits or server errors). "
                "Please wait a moment and try again."
            )
        )

    # No providers had a key configured
    return _LLMResult(
        error=(
            "No AI provider is configured. "
            "Please add a provider API key in Settings."
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Translation
# ─────────────────────────────────────────────────────────────────────────────

async def translate_text(
    text: str,
    target_language: str,
    source_language: str = "auto",
    api_keys: Optional[dict] = None,
) -> str:
    """
    Translate text into the target language.

    Tries deep-translator (Google Translate free) first; falls back to
    LLM-based translation via the primary provider when unavailable.

    Args:
        text:            The text to translate.
        target_language: Target language name or ISO 639-1 code (e.g. "French", "fr").
        source_language: Source language or "auto" for auto-detection.
        api_keys:        Optional provider API keys (unused here, kept for signature compat).

    Returns:
        Formatted markdown string with translated text and metadata.
    """
    if not text or not text.strip():
        return "Error: No text provided for translation."
    if not target_language or not target_language.strip():
        return "Error: No target language specified."

    text = text.strip()

    # ── Attempt 1: deep-translator (Google Translate free endpoint) ──────────
    try:
        from deep_translator import GoogleTranslator
        src = source_language if source_language and source_language.lower() != "auto" else "auto"
        translator = GoogleTranslator(source=src, target=target_language.lower())
        translated = translator.translate(text)
        if translated:
            return (
                f"**Translation** ({source_language} → {target_language})\n\n"
                f"**Original:**\n{text}\n\n"
                f"**Translated:**\n{translated}"
            )
    except ImportError:
        logger.warning("[translate_text] deep-translator not installed, falling back.")
    except Exception as e:
        logger.warning(f"[translate_text] deep-translator failed: {e}. Falling back.")

    # ── Attempt 2: googletrans ──────────────────────────────────────────────
    try:
        from googletrans import Translator
        t = Translator()
        result = t.translate(text, dest=target_language, src=source_language if source_language != "auto" else "auto")
        if result and result.text:
            detected = getattr(result, "src", source_language)
            return (
                f"**Translation** (detected: {detected} → {target_language})\n\n"
                f"**Original:**\n{text}\n\n"
                f"**Translated:**\n{result.text}"
            )
    except ImportError:
        logger.warning("[translate_text] googletrans not installed.")
    except Exception as e:
        logger.warning(f"[translate_text] googletrans failed: {e}. Falling back to LLM.")

    # ── Attempt 3: LLM-based translation fallback ───────────────────────────
    prompt = (
        f"Translate the following text into {target_language}. "
        f"Return ONLY the translated text with no additional commentary:\n\n{text}"
    )
    llm = await _llm_complete(prompt, max_tokens=1024)
    if llm.ok:
        provider_note = f"via {llm.provider}" + (" [fallback]" if llm.fallback_used else "")
        return (
            f"**Translation** (LLM {provider_note} · {source_language} → {target_language})\n\n"
            f"**Original:**\n{text}\n\n"
            f"**Translated:**\n{llm.content}"
        )
    # llm.error already has a clean user-facing message
    return (
        f"Translation to **{target_language}** is currently unavailable.\n\n"
        f"*Reason: {llm.error}*\n\n"
        "You can try again in a moment, or check that a provider API key is configured in Settings."
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Summarization
# ─────────────────────────────────────────────────────────────────────────────

async def summarize_text(
    text: str,
    style: str = "bullet",
    max_length: int = 500,
    api_keys: Optional[dict] = None,
) -> str:
    """
    Summarize text in a specified style.

    Args:
        text:       The text to summarize.
        style:      One of "bullet" (default), "paragraph", or "tldr".
        max_length: Approximate maximum number of words in the summary.
        api_keys:   Optional provider API keys (kept for signature compat).

    Returns:
        Formatted markdown string with the summary.
    """
    if not text or not text.strip():
        return "Error: No text provided for summarization."

    text = text.strip()
    style = style.lower().strip() if style else "bullet"
    if style not in ("bullet", "paragraph", "tldr"):
        style = "bullet"

    word_count = len(text.split())

    style_instructions = {
        "bullet": (
            f"Summarize the following text as a bullet-point list of the key points "
            f"(maximum {max_length} words total). Use markdown bullet points (-)."
        ),
        "paragraph": (
            f"Write a concise summary paragraph (maximum {max_length} words) "
            f"of the following text."
        ),
        "tldr": (
            f"Write a single TL;DR sentence (maximum 50 words) summarizing the "
            f"following text, prefixed with 'TL;DR: '."
        ),
    }

    instruction = style_instructions[style]

    # ── For short texts, do a simple extraction-based summary ───────────────
    if word_count <= 100 and style == "tldr":
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        tldr = sentences[0][:300] if sentences else text[:300]
        return f"**TL;DR:** {tldr}\n\n*(Source text was short; this is the leading sentence.)*"

    # ── LLM-based summarization ──────────────────────────────────────────────
    prompt = f"{instruction}\n\n---\n{text[:8000]}"  # cap at 8k chars input
    llm = await _llm_complete(prompt, max_tokens=max_length * 2)
    if llm.ok:
        label = {"bullet": "Key Points", "paragraph": "Summary", "tldr": "TL;DR"}[style]
        provider_note = f" · {llm.provider}" + (" [fallback]" if llm.fallback_used else "")
        return (
            f"**{label}** *(~{word_count} words → {style} style{provider_note})*\n\n"
            f"{llm.content}"
        )

    # ── Extraction-based fallback when LLM is unavailable ────────────────────
    logger.warning(f"[summarize_text] LLM unavailable ({llm.error}), using extraction fallback.")
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    n = min(5, max(1, max_length // 20))
    extracted = " ".join(sentences[:n])
    return (
        f"**Summary** *(extraction-based · {n} sentence(s) of {len(sentences)})*\n\n"
        f"{extracted}\n\n"
        f"> *Note: AI summarization is temporarily unavailable. {llm.error}*"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Database / SQL Tools
# ─────────────────────────────────────────────────────────────────────────────

def _get_db_path() -> str:
    """Return the SQLite database path from app settings."""
    try:
        from app.core.config import settings
        url = str(settings.DATABASE_URL)
        if url.startswith("sqlite:///"):
            return url[len("sqlite:///"):]
        if url.startswith("sqlite://"):
            return url[len("sqlite://"):]
    except Exception:
        pass
    return "sql_app.db"


async def list_tables(db_path: Optional[str] = None) -> str:
    """
    List all tables in the application's SQLite database.

    Args:
        db_path: Optional path to the SQLite file. Defaults to the app database.

    Returns:
        Markdown-formatted list of table names.
    """
    import sqlite3
    path = db_path or _get_db_path()
    try:
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        if not tables:
            return "No tables found in the database."
        table_list = "\n".join(f"- `{t}`" for t in tables)
        return f"**Database Tables** (`{path}`):\n\n{table_list}\n\n*Total: {len(tables)} tables*"
    except Exception as e:
        logger.error(f"[list_tables] Failed: {e}")
        return f"Error listing tables: {e}"


async def describe_table(table_name: str, db_path: Optional[str] = None) -> str:
    """
    Describe the schema (columns, types) of a specific table.

    Args:
        table_name: Name of the table to describe.
        db_path:    Optional path to the SQLite file.

    Returns:
        Markdown-formatted table schema.
    """
    import sqlite3
    if not table_name or not table_name.strip():
        return "Error: No table name provided."

    # Sanitize: only allow alphanumeric and underscore
    table_name = table_name.strip()
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
        return f"Error: Invalid table name '{table_name}'. Only letters, digits, and underscores are allowed."

    path = db_path or _get_db_path()
    try:
        conn = sqlite3.connect(path)
        cursor = conn.cursor()

        # Check table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
            (table_name,)
        )
        if not cursor.fetchone():
            conn.close()
            return f"Table `{table_name}` does not exist."

        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()

        # Get row count
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
            row_count = cursor.fetchone()[0]
        except Exception:
            row_count = "unknown"

        conn.close()

        if not columns:
            return f"Table `{table_name}` has no columns (empty schema)."

        rows = "\n".join(
            f"| {col[1]} | {col[2]} | {'NOT NULL' if col[3] else 'nullable'} | "
            f"{'PRIMARY KEY' if col[5] else ''} |"
            for col in columns
        )
        return (
            f"**Schema for `{table_name}`** ({row_count} rows)\n\n"
            f"| Column | Type | Nullability | Key |\n"
            f"|--------|------|-------------|-----|\n"
            f"{rows}"
        )
    except Exception as e:
        logger.error(f"[describe_table] Failed: {e}")
        return f"Error describing table '{table_name}': {e}"


_ALLOWED_SQL_PREFIXES = ("SELECT", "PRAGMA", "EXPLAIN", "WITH")
_FORBIDDEN_SQL_PATTERNS = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|REPLACE|TRUNCATE|ATTACH|DETACH)\b',
    re.IGNORECASE
)


async def execute_sql(
    query: str,
    db_path: Optional[str] = None,
    max_rows: int = 50,
) -> str:
    """
    Execute a READ-ONLY SQL query against the application SQLite database.

    Only SELECT, PRAGMA, EXPLAIN, and WITH queries are allowed.
    INSERT / UPDATE / DELETE / DROP and other destructive operations are blocked.

    Args:
        query:    The SQL query to execute.
        db_path:  Optional path to the SQLite file. Defaults to app database.
        max_rows: Maximum number of rows to return (default 50, max 200).

    Returns:
        Markdown-formatted query results table.
    """
    import sqlite3

    if not query or not query.strip():
        return "Error: No SQL query provided."

    query = query.strip()
    max_rows = min(int(max_rows), 200)

    # Security: block destructive statements
    if _FORBIDDEN_SQL_PATTERNS.search(query):
        return (
            "Error: Only read-only queries (SELECT, PRAGMA, EXPLAIN, WITH) are permitted. "
            "Destructive operations are blocked for safety."
        )

    # Check it starts with an allowed keyword
    first_word = query.split()[0].upper()
    if first_word not in _ALLOWED_SQL_PREFIXES:
        return (
            f"Error: Query must start with one of {_ALLOWED_SQL_PREFIXES}. "
            f"Got '{first_word}'."
        )

    path = db_path or _get_db_path()
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute(query)
        rows = cursor.fetchmany(max_rows + 1)
        col_names = [desc[0] for desc in (cursor.description or [])]
        conn.close()

        if not rows:
            return f"Query executed successfully. **No rows returned.**\n\n```sql\n{query}\n```"

        truncated = len(rows) > max_rows
        if truncated:
            rows = rows[:max_rows]

        # Format as markdown table
        header = "| " + " | ".join(col_names) + " |"
        separator = "| " + " | ".join("---" for _ in col_names) + " |"
        body = "\n".join(
            "| " + " | ".join(str(cell) if cell is not None else "NULL" for cell in row) + " |"
            for row in rows
        )
        note = f"\n\n*Showing {len(rows)} row(s)" + (" (truncated)" if truncated else "") + "*"
        return (
            f"**Query Results**\n\n```sql\n{query}\n```\n\n"
            f"{header}\n{separator}\n{body}{note}"
        )
    except sqlite3.OperationalError as e:
        return f"SQL Error: {e}"
    except Exception as e:
        logger.error(f"[execute_sql] Failed: {e}")
        return f"Error executing query: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  Document Search (RAG wrapper)
# ─────────────────────────────────────────────────────────────────────────────

async def search_documents(
    query: str,
    user_id: Optional[str] = None,
    file_type: Optional[str] = None,
    k: int = 5,
    api_keys: Optional[dict] = None,
) -> str:
    """
    Search the user's uploaded documents using vector similarity (RAG).

    Args:
        query:     The search query.
        user_id:   Optional user ID to scope the search to a specific user's documents.
        file_type: Optional filter by file type (e.g. "pdf", "docx", "txt").
        k:         Number of top chunks to retrieve (default 5).
        api_keys:  Optional API keys (kept for signature compat).

    Returns:
        Formatted markdown with the most relevant document excerpts.
    """
    if not query or not query.strip():
        return "Error: No search query provided."

    k = max(1, min(int(k), 20))

    try:
        from app.retrieval.vector_store import VectorStore
        vs = VectorStore()
        # VectorStore.query_relevant_chunks requires user_id: str — use empty string for global search
        effective_user_id = user_id if isinstance(user_id, str) and user_id.strip() else ""
        chunks = await vs.query_relevant_chunks(user_id=effective_user_id, query=query, k=k)

        if not chunks:
            return (
                f"**Document Search:** No relevant chunks found for query: *{query}*\n\n"
                "*(Make sure documents have been uploaded and indexed.)*"
            )

        # Optionally filter by file_type
        if file_type:
            ft = file_type.lower().strip()
            filtered = [c for c in chunks if ft in str(c.get("metadata", {}).get("source", "")).lower()]
            if filtered:
                chunks = filtered

        lines = [f"**Document Search Results** for: *{query}*\n"]
        for i, chunk in enumerate(chunks, 1):
            meta = chunk.get("metadata", {})
            source = meta.get("source", meta.get("filename", "Unknown"))
            page = meta.get("page", "")
            page_str = f" · page {page}" if page else ""
            content = chunk.get("page_content", chunk.get("content", ""))
            score = chunk.get("score", chunk.get("distance", ""))
            score_str = f" (score: {score:.3f})" if isinstance(score, float) else ""
            lines.append(
                f"**[{i}] {source}{page_str}**{score_str}\n"
                f"{content[:500]}{'...' if len(content) > 500 else ''}\n"
            )
        return "\n---\n".join(lines)

    except Exception as e:
        logger.error(f"[search_documents] Failed: {e}")
        return f"Error searching documents: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  Long-context analysis (chunked processing)
# ─────────────────────────────────────────────────────────────────────────────

async def chunk_and_analyze(
    text: str,
    question: str,
    chunk_size: int = 2000,
    api_keys: Optional[dict] = None,
) -> str:
    """
    Analyze a long text relative to a specific question by splitting it into
    chunks, analyzing each, and aggregating the results.

    Useful for documents, long articles, or any text exceeding a single LLM
    context window.

    Args:
        text:       The long text to analyze.
        question:   The question or task to answer from the text.
        chunk_size: Approximate character count per chunk (default 2000).
        api_keys:   Optional API keys (kept for signature compat).

    Returns:
        Aggregated analysis as a formatted markdown string.
    """
    if not text or not text.strip():
        return "Error: No text provided for analysis."
    if not question or not question.strip():
        return "Error: No question provided for analysis."

    text = text.strip()
    question = question.strip()
    chunk_size = max(500, min(int(chunk_size), 8000))

    # ── Split text into chunks with small overlap ────────────────────────────
    overlap = chunk_size // 10
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap

    if not chunks:
        return "Error: Text could not be split into chunks."

    total_chars = len(text)
    num_chunks = len(chunks)

    # ── Analyze each chunk with LLM ──────────────────────────────────────────
    # First call to check provider availability before processing all chunks
    probe_llm = await _llm_complete("Respond with OK", max_tokens=5)
    if not probe_llm.ok:
        return (
            f"**Long-Context Analysis** unavailable\n\n"
            f"**Question:** {question}\n\n"
            f"> *{probe_llm.error}*"
        )

    try:
        partial_answers = []
        provider_note = f"{probe_llm.provider}" + (" [fallback]" if probe_llm.fallback_used else "")

        for i, chunk in enumerate(chunks, 1):
            prompt = (
                f"You are analyzing chunk {i} of {num_chunks} from a larger document "
                f"({total_chars} chars total).\n\n"
                f"Question/Task: {question}\n\n"
                f"Chunk {i}/{num_chunks}:\n{chunk}\n\n"
                f"Provide a concise partial answer based ONLY on this chunk. "
                f"If this chunk is not relevant, say 'Not relevant in this chunk.'"
            )
            llm = await _llm_complete(prompt, max_tokens=512)
            if llm.ok and "not relevant" not in llm.content.lower():
                partial_answers.append(f"**Chunk {i}/{num_chunks}:**\n{llm.content}")
            elif not llm.ok:
                # Transient failure mid-analysis — note it but continue
                logger.warning(f"[chunk_and_analyze] Chunk {i} failed: {llm.error}")

        if not partial_answers:
            return (
                f"**Long-Context Analysis** of {total_chars} chars across {num_chunks} chunks\n\n"
                f"**Question:** {question}\n\n"
                f"No relevant information was found in the provided text for this question."
            )

        # ── Aggregate partial answers ────────────────────────────────────────
        combined = "\n\n".join(partial_answers)
        agg_prompt = (
            f"You analyzed a {total_chars}-character document in {num_chunks} chunks "
            f"to answer this question:\n\n{question}\n\n"
            f"Here are the partial findings from each chunk:\n\n{combined}\n\n"
            f"Now synthesize a single, coherent, comprehensive answer. "
            f"Remove redundancy and organize the information clearly."
        )
        final_llm = await _llm_complete(agg_prompt, max_tokens=1024)
        synthesized = final_llm.content if final_llm.ok else combined

        return (
            f"**Long-Context Analysis** ({total_chars} chars · {num_chunks} chunks · {provider_note})\n\n"
            f"**Question:** {question}\n\n"
            f"**Synthesized Answer:**\n{synthesized}"
        )

    except Exception as e:
        logger.error(f"[chunk_and_analyze] Failed: {e}")
        return f"Error analyzing long context: {e}"
