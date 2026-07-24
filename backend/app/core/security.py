import bcrypt
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
        "aud": settings.JWT_AUDIENCE
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
    """Escapes HTML and strips dangerous tags/protocols (like javascript:) to prevent XSS."""
    if not text:
        return text
    escaped = html.escape(text)
    import re
    # Remove javascript: protocol/schemes to block scripts execution
    cleaned = re.sub(r"javascript\s*:", "", escaped, flags=re.IGNORECASE)
    return cleaned


