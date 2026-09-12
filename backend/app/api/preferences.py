import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.redis_client import cache_get, cache_set
from app.models.user import User, UserPreference
from app.api.auth import get_current_user

logger = logging.getLogger("app.api.preferences")

router = APIRouter(prefix="/preferences", tags=["preferences"])

REDIS_TTL_PREFS = 3600  # 1 hour


class PreferencesUpdate(BaseModel):
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    streaming: Optional[bool] = None
    default_model: Optional[str] = None
    theme: Optional[str] = None
    font_size: Optional[str] = None
    compact_mode: Optional[bool] = None
    contrast_mode: Optional[str] = None
    accent_color: Optional[str] = None
    language: Optional[str] = None
    higher_intelligence: Optional[bool] = None
    enable_dictation: Optional[bool] = None
    improve_model: Optional[bool] = None
    developer_mode: Optional[bool] = None
    system_prompt_override: Optional[str] = None
    features: Optional[Dict[str, Any]] = None


def _serialize_pref(pref: Optional[UserPreference]) -> Dict[str, Any]:
    if not pref:
        return {
            "temperature": 0.7,
            "max_tokens": 2048,
            "streaming": True,
            "default_model": "gemini-3.6-flash",
            "theme": "dark",
            "font_size": "md",
            "compact_mode": False,
            "contrast_mode": "normal",
            "accent_color": "blue",
            "language": "en",
            "higher_intelligence": True,
            "enable_dictation": True,
            "improve_model": True,
            "developer_mode": False,
            "system_prompt_override": None,
            "features": {},
        }
    return {
        "temperature": pref.temperature if pref.temperature is not None else 0.7,
        "max_tokens": pref.max_tokens or 2048,
        "streaming": True if pref.streaming is None else pref.streaming,
        "default_model": pref.default_model or "gemini-3.6-flash",
        "theme": pref.theme or "dark",
        "font_size": pref.font_size or "md",
        "compact_mode": bool(pref.compact_mode),
        "contrast_mode": pref.contrast_mode or "normal",
        "accent_color": pref.accent_color or "blue",
        "language": pref.language or "en",
        "higher_intelligence": True if pref.higher_intelligence is None else bool(pref.higher_intelligence),
        "enable_dictation": True if pref.enable_dictation is None else bool(pref.enable_dictation),
        "improve_model": True if pref.improve_model is None else bool(pref.improve_model),
        "developer_mode": bool(pref.developer_mode),
        "system_prompt_override": pref.system_prompt_override,
        "features": pref.features or {},
    }


@router.get("", response_model=Dict[str, Any])
async def get_user_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve user preferences from Redis cache or database."""
    cache_key = f"user:prefs:{current_user.id}"
    cached = await cache_get(cache_key)
    if cached and isinstance(cached, dict):
        return cached

    stmt = select(UserPreference).where(UserPreference.user_id == current_user.id)
    res = await db.execute(stmt)
    pref = res.scalar_one_or_none()

    data = _serialize_pref(pref)
    await cache_set(cache_key, data, ttl_seconds=REDIS_TTL_PREFS)
    return data


@router.put("", response_model=Dict[str, Any])
async def update_user_preferences(
    payload: PreferencesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update user preferences in both database and Redis."""
    stmt = select(UserPreference).where(UserPreference.user_id == current_user.id)
    res = await db.execute(stmt)
    pref = res.scalar_one_or_none()

    if not pref:
        pref = UserPreference(user_id=current_user.id)
        db.add(pref)

    update_dict = payload.model_dump(exclude_unset=True)
    for k, v in update_dict.items():
        if hasattr(pref, k):
            setattr(pref, k, v)

    await db.commit()
    await db.refresh(pref)

    data = _serialize_pref(pref)
    cache_key = f"user:prefs:{current_user.id}"
    await cache_set(cache_key, data, ttl_seconds=REDIS_TTL_PREFS)
    logger.info(f"[Preferences] Updated and cached preferences for user {current_user.id[:8]}")
    return data
