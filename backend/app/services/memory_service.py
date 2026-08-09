"""
app/services/memory_service.py — Phase 3 multi-category memory service.

Improvements over Phase 1/2:
  • Multi-category support: user_profile, preference, goal, long_term,
    short_term, session, project, topic, fact
  • Semantic deduplication — exact + normalized substring overlap check
  • Conflict resolution — newer memories with higher importance override
    matching older ones
  • Memory expiration — session memories expire after SESSION_MEMORY_TTL seconds
  • Importance scoring — extracted from LLM or inferred by rule
  • project_id / session_id scoping for multi-tenant workspace memories
"""

from __future__ import annotations

import logging
import re
import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Memory, MEMORY_CATEGORIES
from app.core.config import settings
from app.core.redis_client import cache_get, cache_set, cache_delete_pattern

logger = logging.getLogger("app.services.memory_service")

MEMORY_TTL         = 300   # Redis cache TTL (seconds)
SESSION_MEMORY_TTL = 3600  # 1 hour — session memories expire from DB


def _memory_cache_key(user_id: str) -> str:
    return f"memories:{user_id}:list"


class MemoryService:

    # ──────────────────────────────────────────────────────────────────────────
    #  Read helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def get_user_memories(db: AsyncSession, user_id: str) -> List[Memory]:
        """
        Returns all non-expired memories for a user, ordered by importance.
        Results are cached in Redis for MEMORY_TTL seconds.
        """
        cache_key = _memory_cache_key(user_id)
        cached = await cache_get(cache_key)
        if cached is not None:
            logger.debug(f"Memory cache HIT for user {user_id} ({len(cached)} items)")
            return cached  # type: ignore[return-value]

        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Memory)
            .where(
                Memory.user_id == user_id,
                # Filter out expired memories (expires_at IS NULL means no expiry)
                (Memory.expires_at.is_(None)) | (Memory.expires_at > now),
            )
            .order_by(desc(Memory.importance_score))
        )
        memories = list(result.scalars().all())

        serialisable = [
            {
                "id":               m.id,
                "user_id":          m.user_id,
                "category":         m.category,
                "content":          m.content,
                "importance_score": m.importance_score,
                "project_id":       m.project_id,
                "session_id":       m.session_id,
                "expires_at":       str(m.expires_at) if m.expires_at else None,
                "confidence":       m.confidence,
                "created_at":       str(m.created_at),
            }
            for m in memories
        ]
        await cache_set(cache_key, serialisable, ttl_seconds=MEMORY_TTL)
        logger.debug(f"Memory cache MISS — stored {len(memories)} items for user {user_id}")
        return memories

    # ──────────────────────────────────────────────────────────────────────────
    #  Write helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def create_memory(
        db: AsyncSession,
        user_id: str,
        category: str,
        content: str,
        importance_score: int,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        confidence: float = 1.0,
    ) -> Memory:
        """Saves a new memory and invalidates the Redis cache."""
        # Validate category — fallback to 'fact' for unknown values
        if category not in MEMORY_CATEGORIES:
            category = "fact"

        mem = Memory(
            user_id=user_id,
            category=category,
            content=content,
            importance_score=importance_score,
            project_id=project_id,
            session_id=session_id,
            expires_at=expires_at,
            confidence=confidence,
        )
        db.add(mem)
        await db.commit()
        await db.refresh(mem)

        # Sync memory to vector store for semantic retrieval
        try:
            from app.memory.memory_store import MemoryVectorStore
            mem_store = MemoryVectorStore()
            await mem_store.add_memory_item(
                memory_id=str(mem.id),
                user_id=user_id,
                category=category,
                content=content,
                importance_score=importance_score,
                project_id=project_id,
                session_id=session_id,
            )
        except Exception as exc:
            logger.warning(f"Memory vector store sync failed: {exc}")

        # Audit log memory write
        from app.services.audit_service import AuditService
        await AuditService.log_event(
            db, user_id, "memory_write",
            {"memory_id": mem.id, "category": category, "action": "create", "content": content[:100]}
        )

        await cache_delete_pattern(f"memories:{user_id}:*")
        return mem

    @staticmethod
    async def delete_memory(db: AsyncSession, memory_id: str, user_id: str) -> bool:
        """Deletes a memory by id and invalidates the Redis cache."""
        result = await db.execute(
            select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
        )
        mem = result.scalar_one_or_none()
        if not mem:
            return False
        await db.delete(mem)
        await db.commit()

        # Delete from memory vector store
        try:
            from app.memory.memory_store import MemoryVectorStore
            mem_store = MemoryVectorStore()
            await mem_store.delete_memory_item(memory_id)
        except Exception as exc:
            logger.warning(f"Memory vector store delete failed: {exc}")

        # Audit log memory delete
        from app.services.audit_service import AuditService
        await AuditService.log_event(
            db, user_id, "memory_write",
            {"memory_id": memory_id, "action": "delete"}
        )

        await cache_delete_pattern(f"memories:{user_id}:*")
        return True

    # ──────────────────────────────────────────────────────────────────────────
    #  Deduplication & conflict resolution
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.lower().strip(" .!?,"))

    @classmethod
    def _is_duplicate(cls, new_content: str, existing_contents: set) -> bool:
        norm = cls._normalize(new_content)
        if norm in existing_contents:
            return True
        # Substring overlap check (>70% word overlap → duplicate)
        new_words = set(norm.split())
        if len(new_words) < 3:
            return norm in existing_contents
        for existing in existing_contents:
            ex_words = set(existing.split())
            if not ex_words:
                continue
            overlap = len(new_words & ex_words) / max(len(new_words), len(ex_words))
            if overlap > 0.70:
                return True
        return False

    @classmethod
    def _resolve_conflict(
        cls,
        new_content: str,
        new_importance: int,
        existing: Memory,
    ) -> bool:
        """
        Returns True if the new memory should REPLACE the existing one.
        Replacement happens when the new memory has higher importance or
        contains strictly more information (longer content).
        """
        if new_importance > existing.importance_score:
            return True
        if new_importance == existing.importance_score and len(new_content) > len(existing.content):
            return True
        return False

    # ──────────────────────────────────────────────────────────────────────────
    #  Main extraction & persistence pipeline
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def extract_and_save_memories(
        user_id: str,
        chat_id: str,
        user_content: str,
        assistant_content: str,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        """
        FastAPI Background Task to analyze a chat exchange, extract memories,
        deduplicate, resolve conflicts, and persist them.

        Production hardening:
        • Multi-provider fallback: Gemini → Groq → OpenAI → rule-based
          so memory extraction succeeds even when Gemini is rate-limited (HTTP 429).
        • Rule-based extraction is always the final fallback.
        """
        from app.core.database import AsyncSessionLocal
        from app.providers.gemini import GeminiProvider
        from app.providers.groq import GroqProvider
        from app.providers.openai_provider import OpenAIProvider
        from app.providers.openrouter import OpenRouterProvider

        # Fetch all user API keys for multi-provider fallback
        user_keys: dict = {}
        try:
            from app.models.user import ApiKey
            from app.core.security import decrypt_api_key
            from sqlalchemy import select as sa_select
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    sa_select(ApiKey).where(ApiKey.user_id == user_id)
                )
                for key_record in result.scalars().all():
                    pname = (key_record.provider_name or "").lower()
                    user_keys[pname] = decrypt_api_key(key_record.encrypted_api_key)
        except Exception as exc:
            logger.error(f"Failed to fetch user API keys: {exc}")

        # Build multi-provider candidate list for extraction
        extraction_candidates = [
            (GeminiProvider(),     "gemini",     "gemini-2.0-flash",
             user_keys.get("gemini") or user_keys.get("google") or settings.GEMINI_API_KEY),
            (GroqProvider(),       "groq",       "llama-3.3-70b-versatile",
             user_keys.get("groq") or settings.GROQ_API_KEY),
            (OpenAIProvider(),     "openai",     "gpt-4o-mini",
             user_keys.get("openai") or settings.OPENAI_API_KEY),
            (OpenRouterProvider(), "openrouter", "google/gemini-2.0-flash",
             user_keys.get("openrouter") or settings.OPENROUTER_API_KEY),
        ]

        memories_to_create: List[dict] = []
        for prov, prov_name, model, api_key in extraction_candidates:
            if not api_key:
                continue
            try:
                memories_to_create = await _llm_based_extraction(
                    prov, api_key, model, user_content, assistant_content
                )
                if memories_to_create is not None:
                    logger.info(
                        f"[MemoryService] Memory extraction succeeded via '{prov_name}' "
                        f"({len(memories_to_create)} items)"
                    )
                    break
            except Exception as exc:
                err_str = str(exc).lower()
                if "429" in err_str or "rate limit" in err_str:
                    logger.warning(
                        f"[MemoryService] Provider '{prov_name}' rate-limited — "
                        "trying next fallback for memory extraction."
                    )
                else:
                    logger.warning(f"[MemoryService] Provider '{prov_name}' failed: {exc}")
                continue

        if not memories_to_create:
            memories_to_create = _rule_based_extraction(user_content)

        if not memories_to_create:
            return

        async with AsyncSessionLocal() as db:
            # Fetch existing memories for deduplication / conflict resolution
            existing_res = await db.execute(
                select(Memory).where(Memory.user_id == user_id)
            )
            existing_memories: List[Memory] = list(existing_res.scalars().all())
            existing_norm_set = {
                MemoryService._normalize(m.content) for m in existing_memories
            }

            # Build a lookup: normalized content → Memory object (for conflict res)
            existing_map = {
                MemoryService._normalize(m.content): m for m in existing_memories
            }

            for m_data in memories_to_create:
                content   = m_data.get("content", "").strip()
                category  = m_data.get("category", "fact")
                importance = int(m_data.get("importance_score", 5))
                confidence = float(m_data.get("confidence", 1.0))

                if not content:
                    continue

                # Validate category
                if category not in MEMORY_CATEGORIES:
                    category = "fact"

                # Compute expiry for session memories
                expires_at_val: Optional[datetime] = None
                if category == "session":
                    expires_at_val = datetime.now(timezone.utc) + timedelta(
                        seconds=SESSION_MEMORY_TTL
                    )

                norm = MemoryService._normalize(content)

                # Exact duplicate check
                if norm in existing_norm_set:
                    # Conflict resolution: should we update?
                    existing_mem = existing_map.get(norm)
                    if existing_mem and MemoryService._resolve_conflict(
                        content, importance, existing_mem
                    ):
                        await db.execute(
                            update(Memory)
                            .where(Memory.id == existing_mem.id)
                            .values(
                                content=content,
                                importance_score=importance,
                                confidence=confidence,
                            )
                        )
                        logger.info(f"[MemoryService] Updated conflicting memory: {content[:60]}")
                    else:
                        logger.debug(f"[MemoryService] Deduplicated: {content[:60]}")
                    continue

                # Fuzzy duplicate check
                if MemoryService._is_duplicate(content, existing_norm_set):
                    logger.debug(f"[MemoryService] Fuzzy-deduplicated: {content[:60]}")
                    continue

                # Save new memory
                mem = Memory(
                    user_id=user_id,
                    category=category,
                    content=content,
                    importance_score=importance,
                    project_id=project_id,
                    session_id=session_id,
                    expires_at=expires_at_val,
                    confidence=confidence,
                )
                db.add(mem)
                await db.flush()
                existing_norm_set.add(norm)

                # Sync to vector store
                try:
                    from app.memory.memory_store import MemoryVectorStore
                    mem_store = MemoryVectorStore()
                    await mem_store.add_memory_item(
                        memory_id=str(mem.id),
                        user_id=user_id,
                        category=category,
                        content=content,
                        importance_score=importance,
                        project_id=project_id,
                        session_id=session_id,
                        api_key=user_keys.get("gemini") or user_keys.get("google") or settings.GEMINI_API_KEY,  # Gemini key for embeddings
                    )
                except Exception as exc:
                    logger.warning(f"Memory vector store sync failed in extraction: {exc}")

                logger.info(f"[MemoryService] Saved '{category}' memory: {content[:60]}")

            await db.commit()
        await cache_delete_pattern(f"memories:{user_id}:*")


# ─────────────────────────────────────────────────────────────────────────────
#  Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _rule_based_extraction(user_content: str) -> List[dict]:
    """Rule-based memory extraction for fallback mode (strict, high-precision patterns only)."""
    results = []
    text = user_content.strip()

    # Filter out questions, commands, or generic conversational filler
    if any(text.startswith(w) for w in ("what", "how", "why", "when", "where", "can you", "please", "help")):
        return []

    # Exclude common transient states and negative clauses
    _transient_states = (
        "bit", "little", "few", "tired", "hungry", "busy", "sure", "happy",
        "sad", "afraid", "fan", "huge", "big", "student", "human", "bot",
        "don't", "do not", "not", "never", "no", "nothing"
    )

    _rules = [
        (r"\bmy name is ([A-Za-z][A-Za-z\-']{1,25}(?:\s[A-Za-z][A-Za-z\-']{1,25})?)\b", "user_profile", 9,
         lambda m: f"User's name is {m.group(1).strip().title()}"),
        (r"\bi work as (?:a|an) ([A-Za-z0-9_\-\s]{3,35}?)(?:\.|\,|$)", "user_profile", 8,
         lambda m: f"Works as {m.group(1).strip()}"),
        (r"\bi work for ([A-Za-z0-9_\-\s]{2,35}?)(?:\.|\,|$)", "user_profile", 8,
         lambda m: f"Works for {m.group(1).strip()}"),
        (r"\bi prefer ([A-Za-z0-9_\-\s]{5,60}?)(?:\.|\,|because|$)", "preference", 6,
         lambda m: f"Prefers {m.group(1).strip()}"),
        (r"\bmy goal is to ([A-Za-z0-9_\-\s]{5,60}?)(?:\.|\,|$)", "goal", 7,
         lambda m: f"Goal: {m.group(1).strip()}"),
        (r"\b(?:i am|i'm)\s+working on ([A-Za-z0-9_\-\s]{5,60}?)(?:\.|\,|$)", "project", 7,
         lambda m: f"Currently working on: {m.group(1).strip()}"),
    ]

    for pattern, category, score, formatter in _rules:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            extracted = match.group(1).strip() if match.groups() else ""
            if not extracted or any(neg in extracted.lower() for neg in ("not", "never", "don't", "no")):
                continue
            content = formatter(match)
            if 10 <= len(content) <= 100 and not any(ts in content.lower() for ts in _transient_states):
                results.append({
                    "category": category,
                    "content": content,
                    "importance_score": score,
                    "confidence": 0.60,
                })
    return results


async def _llm_based_extraction(
    provider, api_key: str, model: str, user_content: str, assistant_content: str
) -> List[dict]:
    """
    LLM-based memory extraction.

    Accepts any provider instance that implements .generate().
    The model parameter specifies which model to use for this provider.
    Returns [] if extraction fails (caller should try next provider or rule-based fallback).
    """
    system_instruction = (
        "You are an AI memory consolidation module.\n"
        "Extract user facts, preferences, goals, interests, and project context from this conversation.\n"
        "Output ONLY a JSON list. Each item must have:\n"
        "  - 'category': one of user_profile|preference|goal|long_term|short_term|session|project|topic|fact\n"
        "  - 'content': concise third-person statement (e.g. 'Prefers Python over JavaScript')\n"
        "  - 'importance_score': integer 1–10\n"
        "  - 'confidence': float 0.0–1.0 (how confident you are this is a long-term fact)\n"
        "If nothing noteworthy, return []. No markdown, no explanation, raw JSON only."
    )
    conversation_text = f"User: {user_content}\nAssistant: {assistant_content}"
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": f"Analyze this exchange:\n{conversation_text}"},
    ]
    try:
        response = await provider.generate(messages, model="gemini-2.5-flash", api_key=api_key)
        raw_text = response.get("text", "").strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```", 1)[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()
        if raw_text:
            parsed = json.loads(raw_text)
            if isinstance(parsed, list):
                return parsed
    except Exception as exc:
        logger.error(f"[MemoryService] LLM extraction failed: {exc}")
    return []
