"""Request-scoped retrieval of a user's encrypted provider keys.

Keys are decrypted only inside the request that needs them and are returned to
callers as an in-memory mapping.  They must never be logged or persisted in
tool/audit payloads.
"""

from __future__ import annotations

import json
import logging
from typing import Dict

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_api_key
from app.models.user import ApiKey

logger = logging.getLogger(__name__)


async def get_request_provider_keys(
    db: AsyncSession,
    user_id: str,
    request: Request | None = None,
) -> Dict[str, str]:
    result = await db.execute(select(ApiKey).where(ApiKey.user_id == user_id))
    keys: Dict[str, str] = {}
    for record in result.scalars().all():
        provider = (getattr(record, "provider_name", "") or "").lower().strip()
        encrypted = getattr(record, "encrypted_api_key", None)
        if not provider or not encrypted:
            continue
        try:
            keys[provider] = decrypt_api_key(encrypted)
        except Exception:
            logger.warning("Unable to decrypt stored provider key for provider=%s", provider)

    # The existing chat contract supports temporary client keys.  Preserve that
    # behavior for authenticated direct tool endpoints without ever storing them.
    if request:
        raw = request.headers.get("x-api-keys")
        if raw:
            try:
                supplied = json.loads(raw)
                if isinstance(supplied, dict):
                    for provider, key in supplied.items():
                        if isinstance(provider, str) and isinstance(key, str) and key.strip():
                            keys[provider.lower().strip()] = key.strip()
            except (TypeError, ValueError, json.JSONDecodeError):
                logger.warning("Ignoring malformed x-api-keys header")

    if "gemini" in keys and "google" not in keys:
        keys["google"] = keys["gemini"]
    elif "google" in keys and "gemini" not in keys:
        keys["gemini"] = keys["google"]
    return keys
