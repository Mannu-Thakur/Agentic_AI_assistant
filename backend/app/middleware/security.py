import asyncio
import json
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Scope, Receive, Send
from app.core.config import settings
from app.core.security import sanitize_input

logger = logging.getLogger("app.middleware.security")

class SecureHeadersMiddleware(BaseHTTPMiddleware):
    """Adds security headers to every response to prevent clickjacking, XSS, and sniff attacks."""
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https:; "
            "frame-ancestors 'none'"
        )
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        return response


class PayloadLimitMiddleware(BaseHTTPMiddleware):
    """Enforces payload size limits: 5MB for standard JSON and 20MB for document uploads."""
    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("Content-Length")
        if content_length:
            try:
                size = int(content_length)
                path = request.url.path
                
                # Check upload path vs normal path
                if "documents/upload" in path:
                    max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
                else:
                    max_size = 5 * 1024 * 1024  # 5MB standard limit
                
                if size > max_size:
                    from fastapi.responses import JSONResponse
                    logger.warning(f"Payload size {size} bytes exceeds limit of {max_size} bytes on path {path}")
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Payload too large. Request body exceeds allowable limit."}
                    )
            except ValueError:
                pass
        return await call_next(request)


def sanitize_json_data(data: any) -> any:
    """Recursively walks JSON data and sanitizes all string elements."""
    if isinstance(data, dict):
        return {k: sanitize_json_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_json_data(item) for item in data]
    elif isinstance(data, str):
        return sanitize_input(data)
    return data


class InputSanitizationMiddleware:
    """
    ASGI middleware that intercepts application/json requests,
    sanitizes all strings inside the JSON body recursively to block XSS,
    and forwards the cleaned payload.
    """
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check content-type header
        headers = dict(scope.get("headers", []))
        content_type = headers.get(b"content-type", b"").decode("utf-8")

        if "application/json" in content_type:
            # Buffer the request body
            body_chunks = []
            more_body = True
            while more_body:
                message = await receive()
                body_chunks.append(message.get("body", b""))
                more_body = message.get("more_body", False)

            body = b"".join(body_chunks)
            if body:
                try:
                    data = json.loads(body.decode("utf-8"))
                    sanitized_data = sanitize_json_data(data)
                    new_body = json.dumps(sanitized_data).encode("utf-8")
                except Exception:
                    # If JSON parsing fails, let the request proceed to fail validation natively
                    new_body = body
            else:
                new_body = body

            # Create a mock receive channel to feed the sanitized body
            body_sent = False
            async def mock_receive():
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {"type": "http.request", "body": new_body, "more_body": False}
                return await receive()

            await self.app(scope, mock_receive, send)
        else:
            await self.app(scope, receive, send)


# ─────────────────────────────────────────────────────────────────────────────
#  Production Security Guardrails: Injection Defense & Secret Masking
# ─────────────────────────────────────────────────────────────────────────────

import re
from typing import Tuple

class PromptInjectionGuard:
    """Detects direct prompt injection attempts and jailbreaks in user queries."""
    
    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"disregard\s+(all\s+)?prior\s+prompts",
        r"you\s+are\s+now\s+a\s+DAN",
        r"do\s+anything\s+now",
        r"system\s*:\s*override",
        r"override\s+system\s+prompt",
        r"reveal\s+(your\s+)?system\s+prompt",
        r"show\s+me\s+your\s+instructions",
        r"print\s+your\s+initial\s+prompt",
        r"reveal\s+all\s+api\s+keys",
    ]

    @classmethod
    def inspect_prompt(cls, text: str) -> Tuple[bool, str]:
        """Returns (is_suspicious, reason)."""
        if not text:
            return False, ""
        
        lowered = text.lower()
        for pattern in cls.INJECTION_PATTERNS:
            if re.search(pattern, lowered):
                logger.warning(f"[SecurityGuard] Direct prompt injection detected matching pattern: '{pattern}'")
                return True, f"Prompt injection pattern detected: {pattern}"
        
        return False, ""


class IndirectInjectionGuard:
    """Sanitizes third-party untrusted context (web snippets, doc chunks) to prevent indirect prompt injection."""

    INDIRECT_PATTERNS = [
        (r"\[System Context:.*?\]", "[Content Redacted]"),
        (r"\[System Message:.*?\]", "[Content Redacted]"),
        (r"Ignore previous instructions and.*", "[Content Neutralized]"),
        (r"Forget all prior constraints and.*", "[Content Neutralized]"),
    ]

    @classmethod
    def sanitize_external_content(cls, content: str) -> str:
        if not content:
            return content
        
        cleaned = content
        for pattern, replacement in cls.INDIRECT_PATTERNS:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE | re.DOTALL)
        
        return cleaned


class SecretRedactor:
    """Redacts API keys and secrets from logs and LLM output to prevent secret leakage."""

    SECRET_PATTERNS = [
        r"AIzaSy[A-Za-z0-9_-]{20,}",                   # Gemini API key
        r"sk-[A-Za-z0-9_-]{20,}",                      # OpenAI / generic sk key
        r"gsk_[A-Za-z0-9_-]{20,}",                     # Groq key
        r"tvly-[A-Za-z0-9_-]{20,}",                    # Tavily key
        r"Bearer\s+[A-Za-z0-9_\-\.]{20,}",             # Bearer tokens
    ]

    @classmethod
    def redact(cls, text: str) -> str:
        if not text:
            return text
        
        redacted = text
        for pattern in cls.SECRET_PATTERNS:
            redacted = re.sub(pattern, "[REDACTED_API_KEY]", redacted)
        
        return redacted

