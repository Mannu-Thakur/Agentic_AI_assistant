import bcrypt
import uuid
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional
from jose import jwt, JWTError
from app.core.config import settings

def get_password_hash(password: str) -> str:
    # Encrypt password using direct bcrypt library
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)

def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "type": "access",
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_refresh_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "type": "refresh",
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "jti": str(uuid.uuid4()),  # Unique token ID — ensures rotation produces a distinct token
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_token(token: str, token_type: str = "access") -> Optional[str]:
    try:
        # Enforce explicit algorithm check (prevents signature bypass/none algorithm attack)
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE
        )
        if payload.get("type") != token_type:
            return None
        return payload.get("sub")
    except JWTError:
        return None

def is_safe_redirect_url(url: str) -> bool:
    """
    Checks if a redirect URL matches a whitelisted host or relative path.
    Prevents open redirect vulnerabilities and javascript: scheme attacks.
    """
    if not url:
        return True
    from urllib.parse import urlparse
    parsed = urlparse(url)
    
    # Reject dangerous schemes like javascript:
    if parsed.scheme and parsed.scheme.lower() not in ("http", "https"):
        return False
        
    if not parsed.netloc:
        # Relative URLs are safe
        return True
        
    origin = f"{parsed.scheme}://{parsed.netloc}".lower().rstrip("/")
    
    # A-H4 / B-H3 FIX: Removed wildcard *.vercel.app match — it allowed any attacker-
    # controlled vercel.app subdomain as a redirect target. Now only explicitly
    # configured origins in settings are allowed.
    from app.core.config import settings as _cfg
    raw_allowed = list(_cfg.BACKEND_CORS_ORIGINS) + list(_cfg.ALLOWED_REDIRECT_URIS)
    if _cfg.FRONTEND_URL:
        raw_allowed.append(_cfg.FRONTEND_URL)

    allowed_domains = set()
    for allowed in raw_allowed:
        p_all = urlparse(allowed)
        if p_all.netloc:
            allowed_domains.add(f"{p_all.scheme}://{p_all.netloc}".lower().rstrip("/"))
            
    return origin in allowed_domains


def _get_fernet() -> Any:
    import base64
    import hashlib
    from cryptography.fernet import Fernet
    # Derive a 32-byte key from settings.SECRET_KEY
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))

def encrypt_api_key(key: str) -> str:
    f = _get_fernet()
    return f.encrypt(key.encode()).decode()

def decrypt_api_key(encrypted_key: str) -> str:
    f = _get_fernet()
    return f.decrypt(encrypted_key.encode()).decode()


# ── Phase 4 Additions ─────────────────────────────────────────────────────────

import secrets
import html

_in_memory_blacklist = {}

async def blacklist_token(token: str, expires_in_seconds: int) -> None:
    """Blacklists a token in Redis, falling back to an in-memory storage if Redis is down."""
    # MED-1 FIX: purge expired entries on every write so the dict doesn't grow
    # unboundedly in Redis-less (dev) deployments under sustained traffic.
    _now = datetime.now(timezone.utc)
    expired_keys = [k for k, v in _in_memory_blacklist.items() if v <= _now]
    for k in expired_keys:
        _in_memory_blacklist.pop(k, None)

    # B-C1 FIX: Always write to in-memory store first so fallback is always populated,
    # even when Redis is available. This prevents tokens from being unblacklisted if
    # Redis goes down after a logout.
    _in_memory_blacklist[token] = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)

    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            await r.set(f"blacklist:{token}", "1", ex=expires_in_seconds)
    except Exception:
        pass


async def is_token_blacklisted(token: str) -> bool:
    """Checks if a token is blacklisted in Redis or in the in-memory fallback store."""
    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            val = await r.get(f"blacklist:{token}")
            if val is not None:
                return True
    except Exception:
        pass

    # Fallback check
    if token in _in_memory_blacklist:
        if _in_memory_blacklist[token] > datetime.now(timezone.utc):
            return True
        else:
            del _in_memory_blacklist[token]
    return False

async def unblacklist_token(token: str) -> None:
    """Removes a token or user revocation marker from Redis and the in-memory blacklist fallback."""
    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            await r.delete(f"blacklist:{token}")
    except Exception:
        pass

    _in_memory_blacklist.pop(token, None)

def generate_state_token() -> str:
    """Generates a secure state parameter for OAuth flow."""
    return secrets.token_urlsafe(32)

# In-memory and file-backed fallback for OAuth state when Redis is unavailable
# Maps state token -> expiry datetime
_oauth_state_store: dict = {}
_OAUTH_STATE_FILE = Path(__file__).resolve().parent.parent.parent / ".oauth_states_cache.json"


def _load_persistent_oauth_states() -> dict:
    try:
        if _OAUTH_STATE_FILE.is_file():
            with open(_OAUTH_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_persistent_oauth_states(states: dict) -> None:
    try:
        with open(_OAUTH_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(states, f)
    except Exception:
        pass


async def store_oauth_state(state: str, ttl: int = 600) -> None:
    """Stores generated OAuth state in Redis (with in-memory & file-backed fallback when Redis is down)."""
    now = datetime.now(timezone.utc)
    expiry_dt = now + timedelta(seconds=ttl)
    _oauth_state_store[state] = expiry_dt

    try:
        now_iso = now.isoformat()
        states = _load_persistent_oauth_states()
        states = {k: v for k, v in states.items() if isinstance(v, str) and v > now_iso}
        states[state] = expiry_dt.isoformat()
        _save_persistent_oauth_states(states)
    except Exception:
        pass

    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            await r.set(f"oauth_state:{state}", "1", ex=ttl)
    except Exception:
        pass  # Memory + file store is the fallback


async def verify_oauth_state(state: str) -> bool:
    """Verifies and consumes the stored OAuth state parameter (Redis with in-memory & persistent fallback)."""
    if not state or not isinstance(state, str):
        return False
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # Purge expired states from memory store
    expired = [k for k, v in _oauth_state_store.items() if v <= now]
    for k in expired:
        _oauth_state_store.pop(k, None)

    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            val = await r.get(f"oauth_state:{state}")
            if val is not None:
                await r.delete(f"oauth_state:{state}")
                _oauth_state_store.pop(state, None)  # also clean memory
                try:
                    p_states = _load_persistent_oauth_states()
                    if state in p_states:
                        p_states.pop(state, None)
                        _save_persistent_oauth_states(p_states)
                except Exception:
                    pass
                return True
    except Exception:
        pass

    # Check in-memory store
    if state in _oauth_state_store and _oauth_state_store[state] > now:
        del _oauth_state_store[state]
        try:
            p_states = _load_persistent_oauth_states()
            if state in p_states:
                p_states.pop(state, None)
                _save_persistent_oauth_states(p_states)
        except Exception:
            pass
        return True

    # Fallback: check file-backed store (survives worker reload without Redis)
    try:
        p_states = _load_persistent_oauth_states()
        if state in p_states and p_states[state] > now_iso:
            p_states.pop(state, None)
            _save_persistent_oauth_states(p_states)
            return True
    except Exception:
        pass

    return False

def sanitize_input(text: str) -> str:
    """Strips dangerous script tags and protocols (like <script> and javascript:) to prevent XSS without corrupting plain text, code, or math."""
    if not text:
        return text
    import re
    # BUG-8 FIX: Added re.DOTALL so the pattern matches multiline <script> blocks
    # (content containing newlines between opening and closing tags was previously bypassing the filter).
    # Also handles whitespace before '>' in </script > variants via \s*.
    cleaned = re.sub(r"<script\b[^<]*(?:(?!<\/script\s*>)<[^<]*)*<\/script\s*>", "", text, flags=re.IGNORECASE | re.DOTALL)
    # Remove javascript: protocol/schemes to block script execution
    cleaned = re.sub(r"javascript\s*:", "", cleaned, flags=re.IGNORECASE)
    # M-2 FIX: Additional XSS vectors — vbscript, data URIs, and on* event handlers
    cleaned = re.sub(r'(?i)\bvbscript\s*:', '', cleaned)
    cleaned = re.sub(r'(?i)data\s*:\s*text/html', '', cleaned)
    cleaned = re.sub(r'(?i)\bon\w+\s*=', 'on_=', cleaned)  # neutralize on* handlers
    return cleaned


# ── Password Reset Token Helpers ──────────────────────────────────────────────

# In-memory fallback maps: token -> (user_id, expiry) and email -> [timestamps]
_reset_token_store: dict = {}
_reset_rate_limit_store: dict = {}

_TOKEN_FILE = Path(__file__).resolve().parent.parent.parent / ".reset_tokens_cache.json"


def _load_persistent_tokens() -> dict:
    try:
        if _TOKEN_FILE.is_file():
            with open(_TOKEN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_persistent_tokens(tokens: dict) -> None:
    try:
        with open(_TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(tokens, f)
    except Exception:
        pass


async def store_reset_token(token: str, user_id: str, ttl_seconds: int) -> None:
    """Stores a password-reset token mapped to the user_id (Redis + memory + file-backed persistent fallback).
    A-C3 FIX: The raw token is hashed with SHA-256 before being used as a key so that
    a Redis/disk breach cannot be used to redeem active reset tokens directly.
    """
    # A-C3 FIX: hash the raw token; only the hash is persisted
    hashed = hashlib.sha256(token.encode()).hexdigest()

    now = datetime.now(timezone.utc)
    expiry_dt = now + timedelta(seconds=ttl_seconds)
    _reset_token_store[hashed] = (user_id, expiry_dt)

    # Persist to disk so server reloads / worker restarts don't lose active tokens when Redis is absent
    data = _load_persistent_tokens()
    now_iso = now.isoformat()
    # Purge expired entries
    data = {k: v for k, v in data.items() if isinstance(v, dict) and v.get("expires_at", "") > now_iso}
    data[hashed] = {
        "user_id": user_id,
        "expires_at": expiry_dt.isoformat()
    }
    _save_persistent_tokens(data)

    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            await r.set(f"pwd_reset:{hashed}", user_id, ex=ttl_seconds)
    except Exception:
        pass  # memory + persistent store is the fallback


async def verify_reset_token(token: str) -> bool:
    """
    Validates if a password-reset token exists and is active without consuming it.
    Returns True if valid and non-expired, False otherwise.
    """
    if not token or not isinstance(token, str):
        return False
    # A-C3 FIX: hash the raw token before lookup (only hashes are stored)
    hashed = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    # Try Redis first
    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            user_id_bytes = await r.get(f"pwd_reset:{hashed}")
            if user_id_bytes:
                return True
    except Exception:
        pass

    # Fallback 1: check in-memory store
    entry = _reset_token_store.get(hashed)
    if entry:
        _, expiry = entry
        if expiry > now:
            return True

    # Fallback 2: check persistent disk cache
    data = _load_persistent_tokens()
    tok_data = data.get(hashed)
    if tok_data and isinstance(tok_data, dict):
        exp_str = tok_data.get("expires_at")
        if exp_str:
            try:
                exp_dt = datetime.fromisoformat(exp_str)
                if exp_dt > now:
                    return True
            except Exception:
                pass

    return False


async def verify_and_consume_reset_token(token: str) -> Optional[str]:
    """
    Validates and single-use-consumes a password-reset token.
    Returns the associated user_id on success, None on failure/expiry.
    """
    if not token or not isinstance(token, str):
        return None

    # A-C3 FIX: hash the raw token before lookup (only hashes are stored)
    hashed = hashlib.sha256(token.encode()).hexdigest()
    now = datetime.now(timezone.utc)

    # Purge expired in-memory entries
    expired = [k for k, (_, exp) in _reset_token_store.items() if exp <= now]
    for k in expired:
        _reset_token_store.pop(k, None)

    # Try Redis first
    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            # B-C2 FIX: Use atomic GETDEL (Redis 6.2+) to eliminate the TOCTOU
            # race between GET and DELETE where two concurrent requests could both
            # read the same token before either deletes it.
            try:
                user_id_bytes = await r.getdel(f"pwd_reset:{hashed}")
            except Exception:
                # Fallback for Redis < 6.2: Lua script for atomic get+delete
                _lua = """
local v = redis.call('GET', KEYS[1])
if v then redis.call('DEL', KEYS[1]) end
return v
"""
                user_id_bytes = await r.eval(_lua, 1, f"pwd_reset:{hashed}")
            if user_id_bytes:
                _reset_token_store.pop(hashed, None)
                data = _load_persistent_tokens()
                data.pop(hashed, None)
                _save_persistent_tokens(data)
                if isinstance(user_id_bytes, bytes):
                    return user_id_bytes.decode()
                return str(user_id_bytes)
    except Exception:
        pass

    # Fallback 1: check in-memory store
    entry = _reset_token_store.get(hashed)
    if entry:
        user_id, expiry = entry
        if expiry > now:
            del _reset_token_store[hashed]
            data = _load_persistent_tokens()
            data.pop(hashed, None)
            _save_persistent_tokens(data)
            return user_id

    # Fallback 2: check persistent disk cache
    data = _load_persistent_tokens()
    tok_data = data.get(hashed)
    if tok_data and isinstance(tok_data, dict):
        exp_str = tok_data.get("expires_at")
        user_id = tok_data.get("user_id")
        if exp_str and user_id:
            try:
                exp_dt = datetime.fromisoformat(exp_str)
                if exp_dt > now:
                    data.pop(hashed, None)
                    _save_persistent_tokens(data)
                    _reset_token_store.pop(hashed, None)
                    return user_id
            except Exception:
                pass

    return None



async def check_reset_rate_limit(email: str, max_requests: int = 3, window_seconds: int = 900) -> bool:
    """
    Returns True if this email is allowed to request a reset (under rate limit).
    Returns False if the rate limit has been exceeded.
    Uses Redis with in-memory fallback; max_requests per window_seconds (default 3 / 15 min, relaxed in dev).
    """
    # B-H8 FIX: Normalize email so 'User@Example.COM' and 'user@example.com' share the same bucket
    email = email.strip().lower()

    from app.core.config import settings
    if settings.ENVIRONMENT == "development":
        max_requests = max(max_requests, 20)

    key = f"pwd_reset_rl:{email}"
    now = datetime.now(timezone.utc)

    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            # M-7 FIX: Use INCR-first pattern to eliminate the TOCTOU race.
            # The old GET → check → INCR pipeline allowed two concurrent requests to
            # both see count=0, both pass the guard, and both INCR to 1 — effectively
            # granting double the allowed requests at the boundary.
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, window_seconds)
            if count > max_requests:
                return False
            return True
    except Exception:
        pass

    # In-memory fallback: store list of request timestamps
    timestamps = _reset_rate_limit_store.get(email, [])
    cutoff = now - timedelta(seconds=window_seconds)
    timestamps = [t for t in timestamps if t > cutoff]
    if len(timestamps) >= max_requests:
        _reset_rate_limit_store[email] = timestamps
        return False
    timestamps = [t for t in timestamps if t > cutoff]
    if len(timestamps) >= max_requests:
        _reset_rate_limit_store[email] = timestamps
        return False
    timestamps.append(now)
    _reset_rate_limit_store[email] = timestamps
    return True
