"""
app/graph/entity_extractor.py — LLM-based entity extraction pipeline.

Extracts typed, validated entities from document chunks using LLM structured output.
Stores source provenance so every entity can be traced back to its origin chunk.

Supported entity types (domain-relevant for claims/warranty/fraud/enterprise):
  Person, Organization, Policy, Claim, Product, Component,
  Supplier, Transaction, Location, Event, Issue
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from app.core.config import settings

logger = logging.getLogger("app.graph.entity_extractor")

# ── Entity type registry ───────────────────────────────────────────────────────

VALID_ENTITY_TYPES = {
    "Person", "Organization", "Policy", "Claim", "Product",
    "Component", "Supplier", "Transaction", "Location", "Event", "Issue",
    "Date", "Amount", "Regulation", "Process",
}

VALID_RELATIONSHIP_TYPES = {
    "OWNS", "WORKS_FOR", "CLAIMED_ON", "CAUSED_BY", "SUPPLIED_BY",
    "RELATED_TO", "DEPENDS_ON", "MENTIONED_IN", "PURCHASED",
    "INVOLVED_IN", "LOCATED_AT", "REPORTED_BY", "COVERED_BY",
    "ISSUED_BY", "RESULTED_IN",
}

ENTITY_EXTRACTION_PROMPT = """
You are an expert information extraction system for enterprise documents.

Extract all meaningful named entities from the following text chunk.

Return ONLY valid JSON in this exact format:
{
  "entities": [
    {
      "name": "exact name as it appears in text",
      "type": "one of: Person|Organization|Policy|Claim|Product|Component|Supplier|Transaction|Location|Event|Issue|Date|Amount|Regulation|Process",
      "description": "brief description from context (max 100 chars)",
      "confidence": 0.0-1.0
    }
  ],
  "relationships": [
    {
      "source": "entity name",
      "target": "entity name",
      "relationship": "one of: OWNS|WORKS_FOR|CLAIMED_ON|CAUSED_BY|SUPPLIED_BY|RELATED_TO|DEPENDS_ON|MENTIONED_IN|PURCHASED|INVOLVED_IN|LOCATED_AT|REPORTED_BY|COVERED_BY|ISSUED_BY|RESULTED_IN",
      "confidence": 0.0-1.0
    }
  ]
}

Rules:
- Only extract entities explicitly mentioned in the text
- Confidence should reflect how certain you are (> 0.7 = high, 0.4-0.7 = medium, < 0.4 = low)
- Skip generic words; only extract specific named entities
- If no entities found, return {"entities": [], "relationships": []}

Text chunk:
---
{chunk_text}
---

JSON output:
"""


class Entity:
    """Extracted and validated entity."""
    __slots__ = ("id", "name", "type", "description", "confidence", "source_doc_id", "source_chunk_id", "source_text_snippet")

    def __init__(
        self,
        name: str,
        entity_type: str,
        description: str = "",
        confidence: float = 0.8,
        source_doc_id: str = "",
        source_chunk_id: str = "",
        source_text_snippet: str = "",
    ):
        self.id = str(uuid.uuid4())
        self.name = name.strip()
        self.type = entity_type
        self.description = description[:200]
        self.confidence = max(0.0, min(1.0, confidence))
        self.source_doc_id = source_doc_id
        self.source_chunk_id = source_chunk_id
        self.source_text_snippet = source_text_snippet[:300]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "confidence": self.confidence,
            "source_doc_id": self.source_doc_id,
            "source_chunk_id": self.source_chunk_id,
            "source_text_snippet": self.source_text_snippet,
        }


class Relationship:
    """Extracted and validated relationship between two entities."""
    __slots__ = ("id", "source_name", "target_name", "relationship_type", "confidence", "source_doc_id", "source_chunk_id")

    def __init__(
        self,
        source_name: str,
        target_name: str,
        relationship_type: str,
        confidence: float = 0.7,
        source_doc_id: str = "",
        source_chunk_id: str = "",
    ):
        self.id = str(uuid.uuid4())
        self.source_name = source_name.strip()
        self.target_name = target_name.strip()
        self.relationship_type = relationship_type.upper()
        self.confidence = max(0.0, min(1.0, confidence))
        self.source_doc_id = source_doc_id
        self.source_chunk_id = source_chunk_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source_name,
            "target": self.target_name,
            "relationship": self.relationship_type,
            "confidence": self.confidence,
            "source_doc_id": self.source_doc_id,
            "source_chunk_id": self.source_chunk_id,
        }


def _parse_extraction_response(raw_json: str) -> tuple[List[Dict], List[Dict]]:
    """Parse and validate LLM extraction JSON. Returns (entities, relationships)."""
    # Strip markdown code fences
    raw_json = re.sub(r"```(?:json)?\n?", "", raw_json).strip().rstrip("`").strip()
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        # Attempt to extract JSON substring
        match = re.search(r"\{.*\}", raw_json, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("[EntityExtractor] Failed to parse extraction JSON")
                return [], []
        else:
            return [], []

    entities = []
    for e in data.get("entities", []):
        if not isinstance(e, dict):
            continue
        name = str(e.get("name", "")).strip()
        etype = str(e.get("type", "")).strip()
        if not name or len(name) < 2 or len(name) > 200:
            continue
        if etype not in VALID_ENTITY_TYPES:
            continue
        entities.append({
            "name": name,
            "type": etype,
            "description": str(e.get("description", ""))[:200],
            "confidence": float(e.get("confidence", 0.7)),
        })

    relationships = []
    entity_names = {e["name"] for e in entities}
    for r in data.get("relationships", []):
        if not isinstance(r, dict):
            continue
        src = str(r.get("source", "")).strip()
        tgt = str(r.get("target", "")).strip()
        rel = str(r.get("relationship", "")).strip().upper()
        if not src or not tgt or rel not in VALID_RELATIONSHIP_TYPES:
            continue
        # Both source and target must be extracted entities
        if src not in entity_names or tgt not in entity_names:
            continue
        relationships.append({
            "source": src,
            "target": tgt,
            "relationship": rel,
            "confidence": float(r.get("confidence", 0.6)),
        })
    return entities, relationships


async def extract_entities_from_chunk(
    chunk_text: str,
    doc_id: str,
    chunk_id: str,
    api_key: Optional[str] = None,
    min_confidence: float = 0.4,
) -> tuple[List[Entity], List[Relationship]]:
    """
    Extract entities and relationships from a single document chunk.

    Returns (entities, relationships). On any failure, returns ([], []).
    Uses the cheapest available LLM provider (Groq or Gemini flash).
    """
    if not chunk_text or len(chunk_text.strip()) < 50:
        return [], []

    # Truncate very long chunks to avoid token overflow
    text_input = chunk_text[:3000]
    prompt = ENTITY_EXTRACTION_PROMPT.format(chunk_text=text_input)

    raw_response = ""
    try:
        # Try Groq first (cheapest/fastest for extraction)
        if settings.GROQ_API_KEY:
            from app.providers.groq import GroqProvider
            provider = GroqProvider()
            result = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.1-8b-instant",  # cheapest SLM for extraction
                max_tokens=1500,
                temperature=0.1,
                stream=False,
                api_key=settings.GROQ_API_KEY,
            )
            raw_response = result.get("content", "")
        elif settings.GEMINI_API_KEY:
            from app.providers.gemini import GeminiProvider
            provider = GeminiProvider()
            result = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
                model="gemini-2.0-flash-lite",
                max_tokens=1500,
                temperature=0.1,
                stream=False,
                api_key=settings.GEMINI_API_KEY,
            )
            raw_response = result.get("content", "")
        else:
            logger.warning("[EntityExtractor] No LLM API key configured for extraction")
            return [], []
    except Exception as e:
        logger.warning(f"[EntityExtractor] LLM call failed: {e}")
        return [], []

    raw_entities, raw_relationships = _parse_extraction_response(raw_response)

    # Build Entity objects with provenance
    entities: List[Entity] = []
    for e in raw_entities:
        if e["confidence"] < min_confidence:
            continue
        snippet = chunk_text[:150] + "..." if len(chunk_text) > 150 else chunk_text
        entities.append(Entity(
            name=e["name"],
            entity_type=e["type"],
            description=e.get("description", ""),
            confidence=e["confidence"],
            source_doc_id=doc_id,
            source_chunk_id=chunk_id,
            source_text_snippet=snippet,
        ))

    entity_name_set = {ent.name for ent in entities}
    relationships: List[Relationship] = []
    for r in raw_relationships:
        if r["confidence"] < min_confidence:
            continue
        if r["source"] not in entity_name_set or r["target"] not in entity_name_set:
            continue
        relationships.append(Relationship(
            source_name=r["source"],
            target_name=r["target"],
            relationship_type=r["relationship"],
            confidence=r["confidence"],
            source_doc_id=doc_id,
            source_chunk_id=chunk_id,
        ))

    logger.info(
        f"[EntityExtractor] doc={doc_id} chunk={chunk_id[:8]}: "
        f"{len(entities)} entities, {len(relationships)} relationships extracted"
    )
    return entities, relationships
