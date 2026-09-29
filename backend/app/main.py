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
from app.api import auth, chat, documents, memories, api_keys, admin, mcp_servers, metrics as metrics_router, evaluation as evaluation_router

from app.api import health as health_router
from app.api import analytics as analytics_router
from app.api import monitoring as monitoring_router, graph as graph_router
from app.core.database import run_schema_migrations
from app.core.cache_service import get_all_cache_stats


# ─────────────────────────────────────────────────────────────────────────────
#  Structured JSON logger
# ─────────────────────────────────────────────────────────────────────────────

class _JsonFormatter(logging.Formatter):
    """
    Formats each log record as a single-line JSON object.

    BUG-6 FIX: Previously, callers were passing json.dumps({...}) as the log
    message, which caused the formatter to double-encode the JSON string.
    Now the formatter checks if the message is already a JSON string and
    merges it back into the payload instead of double-serializing it.
    Callers should preferably use logger.info("event", extra={...}) pattern,
    but this formatter gracefully handles both patterns.
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        msg = record.getMessage()
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":     record.levelname,
            "logger":    record.name,
        }
        # If the message is already a JSON object (dict), merge its fields
        # directly into the payload to avoid double-encoding.
        if msg and msg.lstrip().startswith("{"):
            try:
                inner = json.loads(msg)
                if isinstance(inner, dict):
                    payload.update(inner)
                else:
                    payload["message"] = msg
            except (json.JSONDecodeError, ValueError):
                payload["message"] = msg
        else:
            payload["message"] = msg
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

# HIGH-2 FIX: module-level set keeps strong references to long-running background
# tasks so Python's GC cannot collect them while the lifespan generator is alive.
_bg_tasks: set = set()



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

    # ── Neo4j Knowledge Graph connection ──────────────────────────────────────
    try:
        from app.graph.neo4j_client import neo4j_client
        connected = await neo4j_client.connect()
        if connected:
            logger.info("[GraphRAG] Neo4j connected and schema initialized.")
        else:
            logger.info("[GraphRAG] Running in vector-only mode (Neo4j not configured).")
    except Exception as e:
        logger.warning(f"[GraphRAG] Neo4j initialization skipped: {e}")

    # ── Orphaned-document recovery ────────────────────────────────────────────
    # Any document left in 'processing' from a previous run (server crash /
    # restart) will never finish — reset them to 'failed' so users can retry.
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.document import Document
        from sqlalchemy.future import select
        async with AsyncSessionLocal() as _db:
            result = await _db.execute(
                select(Document).where(Document.status == "processing")
            )
            stuck_docs = result.scalars().all()
            if stuck_docs:
                for doc in stuck_docs:
                    doc.status = "failed"
                    doc.error_message = (
                        "Indexing was interrupted by a server restart. "
                        "Click Retry to re-index this document."
                    )
                await _db.commit()
                logger.warning(
                    f"[Startup] Reset {len(stuck_docs)} orphaned 'processing' "
                    f"document(s) to 'failed': "
                    f"{[d.filename for d in stuck_docs]}"
                )
    except Exception as _rec_err:
        logger.warning(f"[Startup] Orphaned-document recovery failed (non-fatal): {_rec_err}")

    # Validate provider API keys and emit startup diagnostics
    try:
        from app.providers.registry import provider_registry
        await provider_registry.startup_validate()
    except Exception as _pv_err:
        logger.warning(f"Provider startup validation encountered an issue (non-fatal): {_pv_err}")

    # I-H1 FIX: Instantiate ToolRegistry once and reuse the same singleton across
    # startup and shutdown. Previously ToolRegistry() was called twice, creating two
    # separate instances — shutdown() was a no-op because it ran on the wrong object.
    _tool_registry = None
    try:
        from app.tools.registry import ToolRegistry
        _tool_registry = ToolRegistry()
        await _tool_registry.initialize()
        logger.info("ToolRegistry and MCP servers initialized on startup.")
    except Exception as _tr_err:
        logger.warning(f"ToolRegistry startup initialization warning (non-fatal): {_tr_err}")

    # NEW-LOW-2 FIX: Eagerly initialise the Redis in-memory fallback lock during
    # lifespan startup (inside the running event loop) so the first concurrent
    # pair of requests cannot race on the `_MEM_LOCK is None` check and create
    # two independent Lock objects.
    from app.core.redis_client import _get_mem_lock
    _get_mem_lock()   # creates and caches the asyncio.Lock while event loop is active

    # Start background provider health check task
    # I-H2 FIX: Initialize bg_task to None before the try block so shutdown cannot
    # hit an UnboundLocalError if startup raises before the task is created.
    bg_task = None
    try:
        from app.workers.health_check import provider_health_check_loop
        bg_task = asyncio.create_task(provider_health_check_loop())
        _bg_tasks.add(bg_task)          # HIGH-2 FIX: strong reference prevents GC
        bg_task.add_done_callback(_bg_tasks.discard)  # auto-clean on completion
    except Exception as _bg_err:
        logger.warning(f"Background health-check task failed to start (non-fatal): {_bg_err}")


    yield  # Application runs here

    # ── Shutdown Neo4j ────────────────────────────────────────────────────────
    try:
        from app.graph.neo4j_client import neo4j_client
        await neo4j_client.close()
    except Exception:
        pass

    # ── Shutdown ToolRegistry MCP clients ─────────────────────────────────────
    # I-H1 FIX: Use the same _tool_registry instance from startup, not a new ToolRegistry()
    if _tool_registry is not None:
        try:
            await _tool_registry.shutdown()
        except Exception as _tr_err:
            logger.warning(f"Error shutting down ToolRegistry: {_tr_err}")

    # Shutdown: cancel task
    if bg_task is not None:
        bg_task.cancel()
        try:
            await bg_task
        except asyncio.CancelledError:
            pass
    logger.info("Application shutting down.")



# ─────────────────────────────────────────────────────────────────────────────
#  FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

# M-1 FIX: Hide OpenAPI documentation in production to avoid exposing API surface.
# Docs are only available when DEBUG=True (local development).
_is_debug = getattr(settings, "DEBUG", False)
app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if _is_debug else None,
    docs_url="/docs" if _is_debug else None,
    redoc_url="/redoc" if _is_debug else None,
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
    if isinstance(exc, StarletteHTTPException):
        return await http_exception_handler(request, exc)
    tb = traceback.format_exc()
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}\n{tb}"
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred. Please try again later."},
    )


# ── Phase 4 Security Middlewares ──────────────────────────────────────────────
from app.middleware.security import SecureHeadersMiddleware, PayloadLimitMiddleware, InputSanitizationMiddleware

app.add_middleware(SecureHeadersMiddleware)
app.add_middleware(PayloadLimitMiddleware)
app.add_middleware(InputSanitizationMiddleware)

from app.api import preferences
from app.resume.routes import router as resume_router

app.include_router(auth.router,        prefix=settings.API_V1_STR)
app.include_router(chat.router,        prefix=settings.API_V1_STR)
app.include_router(documents.router,   prefix=settings.API_V1_STR)
app.include_router(memories.router,    prefix=settings.API_V1_STR)
app.include_router(api_keys.router,    prefix=settings.API_V1_STR)
app.include_router(api_keys.providers_router, prefix=settings.API_V1_STR)
app.include_router(health_router.router, prefix=settings.API_V1_STR)
app.include_router(admin.router,        prefix=settings.API_V1_STR)
app.include_router(mcp_servers.router,  prefix=settings.API_V1_STR)
app.include_router(preferences.router,  prefix=settings.API_V1_STR)
app.include_router(metrics_router.router, prefix=settings.API_V1_STR)
app.include_router(evaluation_router.router, prefix=settings.API_V1_STR)
app.include_router(resume_router,       prefix=settings.API_V1_STR)
app.include_router(graph_router.router, prefix=settings.API_V1_STR)
app.include_router(analytics_router.router, prefix=settings.API_V1_STR)
app.include_router(monitoring_router.router, prefix=settings.API_V1_STR)


# ── Cache metrics endpoint ─────────────────────────────────────────────────────
@app.get("/api/v1/metrics/cache", tags=["observability"])
async def get_cache_metrics():
    """Return cache hit/miss statistics for all caches."""
    return {"caches": get_all_cache_stats()}



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
    # Fast-path OPTIONS preflight requests directly to CORSMiddleware
    if request.method == "OPTIONS":
        return await call_next(request)

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
        headers = {}
        origin = request.headers.get("origin")
        if origin and settings.BACKEND_CORS_ORIGINS:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Access-Control-Allow-Credentials"] = "true"
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please slow down."},
            headers=headers,
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


# CORSMiddleware MUST be added LAST so it becomes the outermost middleware,
# ensuring Access-Control-Allow-Origin headers are attached to all responses,
# preflight OPTIONS requests, and unhandled exception responses.
# I-C4 FIX: Tighten CORS — removed wildcard allow_methods/allow_headers and the
# *.vercel.app allow_origin_regex (any Vercel app could make credentialed requests).
# Explicit allowed methods/headers only. Frontend origin is controlled via settings.
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization", "Content-Type", "X-Request-ID",
            "X-API-Key", "x-api-keys", "Accept", "Origin",
            "x-telemetry-enabled", "x-client-time", "x-client-timezone", "x-client-location",
        ],
        expose_headers=["X-Request-ID", "X-Process-Time", "X-Trace-ID"],
    )



# ─────────────────────────────────────────────────────────────────────────────
#  Dev server entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
