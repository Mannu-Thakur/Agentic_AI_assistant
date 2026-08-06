"""
app/agent/doc_signals.py — Dynamic private-document routing signals.

Replaces the static ``_PERSONAL_DOC_SIGNALS`` tuple that previously contained
developer-specific project names (e.g. "myproject", "dashboard", "visualiser feature").

How it works
────────────
``get_user_doc_signals(user_id, db)`` builds a combined signal set for a user:

1. UNIVERSAL_SIGNALS — language-agnostic possession phrases that indicate any
   user is asking about THEIR OWN content ("my resume", "my project", "uploaded",
   etc.).  These are generic and safe for all users.

2. DYNAMIC filename-derived signals — for each document the user has uploaded,
   we extract meaningful tokens from the filename and add them as signals.
   Example: "MyApp_Architecture_v2.pdf" → {"myapp", "architecture"}
            "John_Resume_2026.pdf"     → {"john", "resume"}
   This means signals are only active for the user who actually uploaded that file.

Cache
─────
Results are cached in a module-level LRU dict (max 256 users, TTL = 60 s).
The cache is invalidated by ``invalidate_user_signals(user_id)`` which is called
from document_service whenever a document is added or deleted for that user.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from functools import lru_cache
from typing import FrozenSet, Optional

logger = logging.getLogger("agent.doc_signals")

# ─────────────────────────────────────────────────────────────────────────────
#  Universal signals — safe for all users, no project-specific strings
# ─────────────────────────────────────────────────────────────────────────────

#: Possession / reference phrases that always indicate personal-document intent.
#: These are intentionally GENERIC — no project names, no application names.
UNIVERSAL_SIGNALS: FrozenSet[str] = frozenset({
    # Direct possession phrases
    "my projects", "my project", "my app", "my code", "my bot", "my chatbot",
    "my platform", "my tool", "my system", "my service", "my application",
    "project i made", "project i built", "project i created",
    "project i developed", "project i designed",
    "iot based project", "iot project",
    "my coding platform",
    # Personal profile / resume signals
    "my cgpa", "my gpa", "my xgpa",
    "my resume", "my cv", "my portfolio",
    "my skills", "my education", "my degree",
    "my achievements", "my experience",
    "my internship", "my internships",
    "my grades", "my marks", "my result", "my results",
    "my score", "my background",
    "my profile", "my qualification",
    "my college", "my university", "my institute",
    # Document reference phrases
    "my document", "my file", "my notes",
    "in the file", "from the file",
    "uploaded", "you uploaded", "i uploaded",
    "according to my", "based on my",
    "in my project", "in my app", "in my platform",
})


# ─────────────────────────────────────────────────────────────────────────────
#  In-process filename signal cache (TTL = 60 s, max 256 entries)
# ─────────────────────────────────────────────────────────────────────────────

_CACHE_TTL = 60.0           # seconds — short enough to pick up new uploads
_CACHE_MAX = 256            # max distinct user_ids cached at once
_MIN_TOKEN_LEN = 3          # ignore tokens shorter than this (e.g. "v2", "my")
_MAX_TOKEN_LEN = 40         # ignore unreasonably long tokens

# Structure: {user_id: (expiry_timestamp, frozenset_of_signals)}
_signal_cache: dict[str, tuple[float, FrozenSet[str]]] = {}
_cache_lock = asyncio.Lock()


def _extract_filename_tokens(filename: str) -> FrozenSet[str]:
    """
    Convert a filename into a set of meaningful lowercase tokens.

    Examples:
        "MyApp_Architecture_v2.pdf"       → {"myapp", "architecture"}
        "John_Resume_2026.docx"          → {"john", "resume"}
        "My Food Tracking System.pdf"    → {"food", "tracking", "system"}
        "IoT_Sensor_Board_Project.pdf"   → {"iot", "sensor", "board", "project"}
    """
    # Strip extension
    base = os.path.splitext(filename)[0]
    # Split on non-alphanumeric characters (underscores, dashes, spaces, dots)
    raw_tokens = re.split(r"[^a-zA-Z0-9]+", base)
    tokens: set[str] = set()
    for tok in raw_tokens:
        tok_lower = tok.lower()
        # Skip purely numeric tokens (version numbers, years)
        if tok_lower.isdigit():
            continue
        # Skip tokens that are too short or too long
        if len(tok_lower) < _MIN_TOKEN_LEN or len(tok_lower) > _MAX_TOKEN_LEN:
            continue
        # Skip common generic filler words that appear in almost every filename
        if tok_lower in {
            "the", "and", "for", "with", "new", "old", "final",
            "copy", "draft", "doc", "file", "pdf", "docx", "xlsx",
            "ver", "version", "rev", "updated", "latest", "backup",
        }:
            continue
        tokens.add(tok_lower)
    return frozenset(tokens)


async def _fetch_user_filename_signals(user_id: str) -> FrozenSet[str]:
    """
    Query the database for all filenames uploaded by ``user_id`` and convert
    them into routing signal tokens.

    Returns an empty frozenset if the DB is unreachable (non-fatal).
    """
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.document_service import DocumentService

        async with AsyncSessionLocal() as db:
            docs = await DocumentService.get_user_documents(db, user_id)

        tokens: set[str] = set()
        for doc in docs:
            tokens.update(_extract_filename_tokens(doc.filename))

        return frozenset(tokens)
    except Exception as exc:
        logger.warning(
            f"[DocSignals] Could not fetch filenames for user={user_id}: {exc}"
        )
        return frozenset()


async def get_user_doc_signals(user_id: str) -> FrozenSet[str]:
    """
    Return the combined set of private-document routing signals for ``user_id``.

    Combines:
      • UNIVERSAL_SIGNALS (generic possession/reference phrases)
      • Filename-derived tokens from the user's uploaded documents

    The result is cached for ``_CACHE_TTL`` seconds and is invalidated when
    the user adds or deletes a document (via ``invalidate_user_signals``).
    """
    now = time.monotonic()

    async with _cache_lock:
        entry = _signal_cache.get(user_id)
        if entry is not None:
            expiry, cached_signals = entry
            if now < expiry:
                return cached_signals
            # Expired — evict and re-fetch below
            del _signal_cache[user_id]

        # Evict oldest entries if cache is full
        if len(_signal_cache) >= _CACHE_MAX:
            oldest_uid = min(_signal_cache, key=lambda k: _signal_cache[k][0])
            del _signal_cache[oldest_uid]

        # Fetch filename tokens from DB (inside the lock is fine — async, non-blocking)
        filename_tokens = await _fetch_user_filename_signals(user_id)
        combined = UNIVERSAL_SIGNALS | filename_tokens

        _signal_cache[user_id] = (now + _CACHE_TTL, combined)
        logger.debug(
            f"[DocSignals] Built signal set for user={user_id}: "
            f"{len(combined)} signals ({len(filename_tokens)} from filenames)"
        )
        return combined


def invalidate_user_signals(user_id: str) -> None:
    """
    Evict the cached signal set for ``user_id``.

    Must be called from document_service whenever a document is added or
    deleted for this user so the next query rebuilds from fresh filenames.

    Thread-safe: operates on the dict synchronously (single-key deletion is
    atomic in CPython under the GIL).
    """
    _signal_cache.pop(user_id, None)
    logger.debug(f"[DocSignals] Cache invalidated for user={user_id}")


def query_matches_user_signals(query: str, signals: FrozenSet[str]) -> bool:
    """
    Return True if the lowercased query contains ANY signal from ``signals``.

    This is the drop-in replacement for:
        any(sig in query.lower() for sig in _PERSONAL_DOC_SIGNALS)
    """
    q_lower = query.lower()
    return any(sig in q_lower for sig in signals)


def classify_sub_questions(
    sub_questions: list[str],
    signals: FrozenSet[str],
) -> tuple[list[str], list[str]]:
    """
    Split a list of sub-questions into public and private groups.

    Returns:
        (public_sub_questions, private_sub_questions)

    Drop-in replacement for the two list-comprehensions in grade_documents_node
    and retrieve_context_node that previously filtered against _PERSONAL_DOC_SIGNALS.
    """
    public: list[str] = []
    private: list[str] = []
    for sq in sub_questions:
        if query_matches_user_signals(sq, signals):
            private.append(sq)
        else:
            public.append(sq)
    return public, private
