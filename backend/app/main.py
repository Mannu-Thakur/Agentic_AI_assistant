"""
main.py — FastAPI application entry point.

Changes vs original:
  • Structured JSON logging (one JSON object per log line) for easy ingestion
    by log aggregators (Loki, CloudWatch, Datadog).
  • X-Request-ID header generated per request and propagated through logs.
  • /health router (moved out of main, now in api/health.py) with the new
    /health/providers endpoint.
  • Rate-limit middleware using Redis (100 req/min per IP, fails open).
"""

import time
import uuid
import json
import logging
import logging.config
from contextlib import asynccontextmanager

import traceback
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.api import auth, chat, documents, memories, api_keys, admin, mcp_servers, metrics as metrics_router

from app.api import health as health_router
from app.core.database import run_schema_migrations
from app.core.cache_service import get_all_cache_stats


# ─────────────────────────────────────────────────────────────────────────────
#  Structured JSON logger
# ─────────────────────────────────────────────────────────────────────────────

class _JsonFormatter(logging.Formatter):
    """Formats each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


logging.config.dictConfig({
    "version":    1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": _JsonFormatter},
    },
    "handlers": {
        "console": {
            "class":     "logging.StreamHandler",
            "formatter": "json",
            "stream":    "ext://sys.stdout",
        },
    },
    "root": {
        "level":    "INFO",
        "handlers": ["console"],
    },
})

logger = logging.getLogger("main")


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run safe database schema migrations on startup."""
    import asyncio
    try:
        run_schema_migrations()
        logger.info("Schema migrations completed successfully.")
    except Exception as e:
        logger.error(f"Schema migration failed: {e}")
    
    # Validate provider API keys and emit startup diagnostics
    try:
        from app.providers.registry import provider_registry
        await provider_registry.startup_validate()
    except Exception as _pv_err:
        logger.warning(f"Provider startup validation encountered an issue (non-fatal): {_pv_err}")

    # Start background provider health check task
    from app.workers.health_check import provider_health_check_loop
    bg_task = asyncio.create_task(provider_health_check_loop())
    
    yield  # Application runs here
    
    # Shutdown: cancel task
    bg_task.cancel()
    try:
        await bg_task
    except asyncio.CancelledError:
        pass
    logger.info("Application shutting down.")


# ─────────────────────────────────────────────────────────────────────────────
#  FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Global exception handlers ─────────────────────────────────────────────────

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Pass-through HTTPExceptions with a consistent JSON body."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return 422 validation errors in a consistent JSON shape."""
    errors = []
    for error in exc.errors():
        errors.append({
            "field": " -> ".join(str(loc) for loc in error.get("loc", [])),
            "message": error.get("msg", "Validation error"),
        })
    return JSONResponse(
        status_code=422,
        content={"detail": "Request validation failed.", "errors": errors},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catch-all for any unhandled exception.
    Logs the full stack trace server-side but returns only a generic 500
    to the client — preventing internal implementation details from leaking.
    """
    tb = traceback.format_exc()
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}\n{tb}"
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."},
    )


if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID", "x-api-keys", "x_api_keys"],
        expose_headers=["X-Request-ID", "X-Process-Time", "X-Trace-ID"],
    )

# ── Phase 4 Security Middlewares ──────────────────────────────────────────────
from app.middleware.security import SecureHeadersMiddleware, PayloadLimitMiddleware, InputSanitizationMiddleware

app.add_middleware(SecureHeadersMiddleware)
app.add_middleware(PayloadLimitMiddleware)
app.add_middleware(InputSanitizationMiddleware)

app.include_router(auth.router,        prefix=settings.API_V1_STR)
app.include_router(chat.router,        prefix=settings.API_V1_STR)
app.include_router(documents.router,   prefix=settings.API_V1_STR)
app.include_router(memories.router,    prefix=settings.API_V1_STR)
app.include_router(api_keys.router,    prefix=settings.API_V1_STR)
app.include_router(api_keys.providers_router, prefix=settings.API_V1_STR)
app.include_router(health_router.router, prefix=settings.API_V1_STR)
app.include_router(admin.router,        prefix=settings.API_V1_STR)
app.include_router(mcp_servers.router,  prefix=settings.API_V1_STR)
app.include_router(metrics_router.router, prefix=settings.API_V1_STR)


# ── Cache metrics endpoint ─────────────────────────────────────────────────────
@app.get("/api/v1/metrics/cache", tags=["observability"])
async def get_cache_metrics():
    """Return cache hit/miss statistics for all caches."""
    return {"caches": get_all_cache_stats()}

# (CORS registered above, before security middlewares — see line ~97)


# ─────────────────────────────────────────────────────────────────────────────
#  Middleware
# ─────────────────────────────────────────────────────────────────────────────

@app.middleware("http")
async def request_lifecycle_middleware(request: Request, call_next):
    """
    Per-request middleware that:
      1. Generates a unique X-Request-ID.
      2. Parses/generates W3C Trace Context (traceparent) headers.
      3. Applies a Redis-backed rate limit (100 req/min per IP, fails open).
      4. Measures wall-clock latency and adds X-Process-Time header.
      5. Records Prometheus HTTP request metrics.
      6. Emits a structured JSON access log line containing trace contexts.
    """
    request_id = str(uuid.uuid4())[:8]
    client_ip  = request.client.host if request.client else "unknown"

    # W3C Trace Context propagation
    traceparent = request.headers.get("traceparent")
    trace_id = None
    span_id = None
    if traceparent:
        parts = traceparent.split("-")
        if len(parts) >= 3:
            trace_id = parts[1]
            span_id = parts[2]
    
    if not trace_id:
        import secrets
        trace_id = secrets.token_hex(16)
        span_id = secrets.token_hex(8)

    # ── Rate limiting (soft, fails open) ──────────────────────────────────────
    if client_ip in ("127.0.0.1", "localhost", "::1", "testclient"):
        allowed = True
    else:
        from app.core.redis_client import rate_limit_check
        allowed = await rate_limit_check(
            key=f"ratelimit:{client_ip}",
            limit=100,
            window_seconds=60,
        )
    if not allowed:
        from fastapi.responses import JSONResponse
        logger.warning(json.dumps({
            "event":      "rate_limited",
            "client_ip":  client_ip,
            "request_id": request_id,
            "trace_id":   trace_id,
            "span_id":    span_id,
            "path":       request.url.path,
        }))
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down."},
        )

    start = time.perf_counter()
    response: Response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 1)

    # Record Prometheus metrics
    from app.core.metrics import metrics_collector
    metrics_collector.record_request(request.method, request.url.path, response.status_code, elapsed_ms)

    response.headers["X-Request-ID"]   = request_id
    response.headers["X-Process-Time"] = f"{elapsed_ms}ms"
    response.headers["X-Trace-ID"]     = trace_id
    response.headers["X-Span-ID"]      = span_id

    logger.info(json.dumps({
        "event":        "http_request",
        "request_id":   request_id,
        "trace_id":     trace_id,
        "span_id":      span_id,
        "method":       request.method,
        "path":         request.url.path,
        "status":       response.status_code,
        "duration_ms":  elapsed_ms,
        "client_ip":    client_ip,
    }))

    return response


# ─────────────────────────────────────────────────────────────────────────────
#  Dev server entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
