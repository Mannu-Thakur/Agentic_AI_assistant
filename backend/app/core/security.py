import bcrypt
import uuid
import json
from pathlib import Path
from datetime import datetime, timedelta
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
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
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
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
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
        
    # Check against settings CORS origins or ALLOWED_REDIRECT_URIS
    origin = f"{parsed.scheme}://{parsed.netloc}"
    allowed_domains = set(settings.BACKEND_CORS_ORIGINS) | set(settings.ALLOWED_REDIRECT_URIS)
    
    # Also parse ALLOWED_REDIRECT_URIS individually
    for allowed in settings.ALLOWED_REDIRECT_URIS:
        p_all = urlparse(allowed)
        if p_all.netloc:
            allowed_domains.add(f"{p_all.scheme}://{p_all.netloc}")
            
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
    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            await r.setex(f"blacklist:{token}", expires_in_seconds, "1")
            return
    except Exception:
        pass
    
    # Fallback to in-memory blacklist
    from datetime import datetime, timedelta
    _in_memory_blacklist[token] = datetime.utcnow() + timedelta(seconds=expires_in_seconds)

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
        from datetime import datetime
        if _in_memory_blacklist[token] > datetime.utcnow():
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

# In-memory fallback for OAuth state when Redis is unavailable
# Maps state token -> expiry datetime
_oauth_state_store: dict = {}

async def store_oauth_state(state: str, ttl: int = 600) -> None:
    """Stores generated OAuth state in Redis (with in-memory fallback when Redis is down)."""
    # Always store in memory as a reliable fallback
    _oauth_state_store[state] = datetime.utcnow() + timedelta(seconds=ttl)
    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            await r.setex(f"oauth_state:{state}", ttl, "1")
    except Exception:
        pass  # Memory store is the fallback

async def verify_oauth_state(state: str) -> bool:
    """Verifies and consumes the stored OAuth state parameter (Redis with in-memory fallback)."""
    # Purge expired states from memory store
    now = datetime.utcnow()
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
                return True
    except Exception:
        pass

    # Fallback: check in-memory store
    if state in _oauth_state_store and _oauth_state_store[state] > now:
        del _oauth_state_store[state]
        return True

    return False

def sanitize_input(text: str) -> str:
    """Strips dangerous script tags and protocols (like <script> and javascript:) to prevent XSS without corrupting plain text, code, or math."""
    if not text:
        return text
    import re
    # Remove <script ...>...</script> tags
    cleaned = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>", "", text, flags=re.IGNORECASE)
    # Remove javascript: protocol/schemes to block script execution
    cleaned = re.sub(r"javascript\s*:", "", cleaned, flags=re.IGNORECASE)
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
    """Stores a password-reset token mapped to the user_id (Redis + memory + file-backed persistent fallback)."""
    expiry_dt = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    _reset_token_store[token] = (user_id, expiry_dt)

    # Persist to disk so server reloads / worker restarts don't lose active tokens when Redis is absent
    data = _load_persistent_tokens()
    now_iso = datetime.utcnow().isoformat()
    # Purge expired entries
    data = {k: v for k, v in data.items() if isinstance(v, dict) and v.get("expires_at", "") > now_iso}
    data[token] = {
        "user_id": user_id,
        "expires_at": expiry_dt.isoformat()
    }
    _save_persistent_tokens(data)

    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            await r.setex(f"pwd_reset:{token}", ttl_seconds, user_id)
    except Exception:
        pass  # memory + persistent store is the fallback


async def verify_reset_token(token: str) -> bool:
    """
    Validates if a password-reset token exists and is active without consuming it.
    Returns True if valid and non-expired, False otherwise.
    """
    if not token or not isinstance(token, str):
        return False
    now = datetime.utcnow()

    # Try Redis first
    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            user_id_bytes = await r.get(f"pwd_reset:{token}")
            if user_id_bytes:
                return True
    except Exception:
        pass

    # Fallback 1: check in-memory store
    entry = _reset_token_store.get(token)
    if entry:
        _, expiry = entry
        if expiry > now:
            return True

    # Fallback 2: check persistent disk cache
    data = _load_persistent_tokens()
    tok_data = data.get(token)
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

    now = datetime.utcnow()

    # Purge expired in-memory entries
    expired = [k for k, (_, exp) in _reset_token_store.items() if exp <= now]
    for k in expired:
        _reset_token_store.pop(k, None)

    # Try Redis first
    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            user_id_bytes = await r.get(f"pwd_reset:{token}")
            if user_id_bytes:
                # Consume immediately (single-use)
                await r.delete(f"pwd_reset:{token}")
                _reset_token_store.pop(token, None)
                data = _load_persistent_tokens()
                data.pop(token, None)
                _save_persistent_tokens(data)
                if isinstance(user_id_bytes, bytes):
                    return user_id_bytes.decode()
                return str(user_id_bytes)
    except Exception:
        pass

    # Fallback 1: check in-memory store
    entry = _reset_token_store.get(token)
    if entry:
        user_id, expiry = entry
        if expiry > now:
            del _reset_token_store[token]
            data = _load_persistent_tokens()
            data.pop(token, None)
            _save_persistent_tokens(data)
            return user_id

    # Fallback 2: check persistent disk cache
    data = _load_persistent_tokens()
    tok_data = data.get(token)
    if tok_data and isinstance(tok_data, dict):
        exp_str = tok_data.get("expires_at")
        user_id = tok_data.get("user_id")
        if exp_str and user_id:
            try:
                exp_dt = datetime.fromisoformat(exp_str)
                if exp_dt > now:
                    data.pop(token, None)
                    _save_persistent_tokens(data)
                    _reset_token_store.pop(token, None)
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
    from app.core.config import settings
    if settings.ENVIRONMENT == "development":
        max_requests = max(max_requests, 20)

    key = f"pwd_reset_rl:{email.lower()}"
    now = datetime.utcnow()

    try:
        from app.core.redis_client import get_redis
        r = await get_redis()
        if r:
            count_bytes = await r.get(key)
            count = int(count_bytes) if count_bytes else 0
            if count >= max_requests:
                return False
            # Increment; set TTL only on first request
            pipe = r.pipeline()
            pipe.incr(key)
            if count == 0:
                pipe.expire(key, window_seconds)
            await pipe.execute()
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
    timestamps.append(now)
    _reset_rate_limit_store[email] = timestamps
    return True
