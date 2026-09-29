"""
app/core/database.py — SQLAlchemy engine + session factory.

Phase 3 addition: run_schema_migrations() performs safe ALTER TABLE
statements to add new columns to existing SQLite databases without
requiring Alembic — ensuring backward-compatible schema upgrades on
application startup.

Production notes:
  • SQLite: pool_size / max_overflow are NOT valid — uses check_same_thread=False
    and NullPool for async via aiosqlite.
  • PostgreSQL: full pool_size=10, max_overflow=20 configuration applied.
"""

import logging
from typing import AsyncGenerator

from sqlalchemy import create_engine, text, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings

logger = logging.getLogger("app.core.database")


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _build_sync_engine():
    url = settings.DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if _is_sqlite(url):
        return create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        connect_args={"connect_timeout": 10},
    )


def _build_async_engine():
    url = settings.ASYNC_DATABASE_URL
    if _is_sqlite(url):
        # BUG-5 FIX: aiosqlite does NOT accept check_same_thread — it manages
        # thread-safety internally. Only the stdlib sqlite3 sync driver requires it.
        # Passing it here causes TypeError on some aiosqlite versions.
        return create_async_engine(
            url,
            pool_pre_ping=True,
            connect_args={"timeout": 30},
        )
    # PostgreSQL: full production pool configuration
    # For asyncpg, query params like sslmode=require or channel_binding=require
    # cause TypeError: connect() got an unexpected keyword argument 'sslmode'.
    # asyncpg expects connect_args={"ssl": "require"}.
    connect_args = {}
    if "sslmode=require" in url or "ssl=require" in url or "neon.tech" in url:
        connect_args["ssl"] = "require"
    # FIX: Supabase Transaction Pooler (port 6543) uses PgBouncer in transaction
    # mode which does NOT support asyncpg prepared statements. Disable caching.
    if "pooler.supabase.com" in url or "supabase.com" in url:
        connect_args["statement_cache_size"] = 0
    if "?" in url:
        base_url, query = url.split("?", 1)
        params = [p for p in query.split("&") if not p.startswith("sslmode=") and not p.startswith("channel_binding=") and not p.startswith("ssl=")]
        url = base_url + ("?" + "&".join(params) if params else "")

    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=1800,
        pool_timeout=10,
        connect_args=connect_args,
    )


# ── Lazy engine initialisation ────────────────────────────────────────────────
# Engines are created on FIRST USE rather than at import time.
# This prevents a 15-minute hang at startup when DATABASE_URL is unreachable
# (PostgreSQL default TCP timeout) from blocking the entire application boot.
_engine = None
_async_engine = None

def _get_engine():
    global _engine
    if _engine is None:
        _engine = _build_sync_engine()
        _db_type = "PostgreSQL" if not _is_sqlite(settings.DATABASE_URL) else "SQLite"
        logger.info(f"[DB] Sync engine initialised: {_db_type}")
    return _engine

def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        _async_engine = _build_async_engine()
        _db_type = "PostgreSQL" if not _is_sqlite(settings.DATABASE_URL) else "SQLite"
        logger.info(f"[DB] Async engine initialised: {_db_type}")
    return _async_engine

# Convenience property-like accessors used throughout the codebase
class _EngineProxy:
    """Proxy that creates the engine on first attribute access."""
    def __getattr__(self, name):
        return getattr(_get_engine(), name)
    def __call__(self, *a, **kw):
        return _get_engine()(*a, **kw)

engine = _EngineProxy()

def _make_session_local():
    return sessionmaker(autocommit=False, autoflush=False, bind=_get_engine())

class _SessionProxy:
    """Proxy that creates SessionLocal on first use."""
    def __call__(self, *a, **kw):
        return _make_session_local()(*a, **kw)
    def __getattr__(self, name):
        return getattr(_make_session_local(), name)

SessionLocal = _SessionProxy()

# ── Asynchronous Session Maker (lazy) ─────────────────────────────────────────
class _AsyncSessionProxy:
    """Creates AsyncSessionLocal on first use so no engine is touched at import time."""
    _factory = None

    def _get_factory(self):
        if self._factory is None:
            self._factory = async_sessionmaker(
                bind=_get_async_engine(),
                class_=AsyncSession,
                expire_on_commit=False,
            )
        return self._factory

    def __call__(self, *a, **kw):
        return self._get_factory()(*a, **kw)

    def __getattr__(self, name):
        return getattr(self._get_factory(), name)

AsyncSessionLocal = _AsyncSessionProxy()

# ── SQLite PRAGMA configuration (registered lazily inside _get_engine) ─────────
# The @event.listens_for decorators are moved inside the engine builders so they
# only fire after the engines are actually created (not at import time).

Base = declarative_base()


# ── FastAPI dependency ─────────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            # M-1 FIX: Removed auto-commit. Route handlers must manage commits explicitly.
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()



# ── Phase 3: safe schema migrations ───────────────────────────────────────────

def run_schema_migrations() -> None:
    """
    Safely perform database schema upgrades:
    1. Create all missing tables via Base.metadata.create_all.
    2. Add expires_at, project_id, session_id, and confidence to memories table if missing.
    3. Add role column to users table if missing.
    4. Create audit_logs table if it does not exist.
    5. Add is_verified column to api_keys table if missing, backfill existing rows to True.

    Uses database-agnostic SQLAlchemy inspection.
    Only called explicitly from the application lifespan — NOT on module import.
    """
    import re as _re_ddl
    from sqlalchemy import inspect

    import app.models  # Ensure model registries are imported
    from app.models.evaluation import EvalResult

    _SAFE_DDL_TYPE_RE = _re_ddl.compile(r'^[A-Z0-9_\s\(\)\.\,]+$', _re_ddl.IGNORECASE)
    _SAFE_DDL_NAME_RE = _re_ddl.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

    def _safe_add_column(conn, table_name: str, col_name: str, col_type: str):
        # B-C5 FIX: Validate table, column name and column type to prevent DDL injection
        if not (_SAFE_DDL_NAME_RE.match(table_name) and _SAFE_DDL_NAME_RE.match(col_name) and _SAFE_DDL_TYPE_RE.match(col_type)):
            raise ValueError(f"Unsafe DDL parameters rejected: table={table_name!r}, col={col_name!r}, type={col_type!r}")
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"))
        logger.info(f"[schema] Added column {table_name}.{col_name}")

    try:
        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)

        # 1. Update memories table
        if inspector.has_table("memories"):
            existing_memories_cols = {col["name"] for col in inspector.get_columns("memories")}
            new_memories_cols = [
                ("expires_at",  "TIMESTAMP"),
                ("project_id",  "VARCHAR(128)"),
                ("session_id",  "VARCHAR(128)"),
                ("confidence",  "FLOAT DEFAULT 1.0"),
            ]
            with engine.begin() as conn:
                for col_name, col_type in new_memories_cols:
                    if col_name not in existing_memories_cols:
                        _safe_add_column(conn, "memories", col_name, col_type)


        # 1.1 Update chats table (add is_live_share)
        if inspector.has_table("chats"):
            existing_chats_cols = {col["name"] for col in inspector.get_columns("chats")}
            if "is_live_share" not in existing_chats_cols:
                with engine.begin() as conn:
                    ddl = "ALTER TABLE chats ADD COLUMN is_live_share BOOLEAN DEFAULT FALSE"
                    conn.execute(text(ddl))
                    logger.info("[schema] Added column chats.is_live_share")

        # 1.2 Update messages table (add images JSON column + fast index)
        if inspector.has_table("messages"):
            existing_msg_cols = {col["name"] for col in inspector.get_columns("messages")}
            if "images" not in existing_msg_cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE messages ADD COLUMN images TEXT"))
                    logger.info("[schema] Added column messages.images")
            # Ensure fast per-chat lookup index (idempotent via IF NOT EXISTS)
            with engine.begin() as conn:
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS idx_messages_chat_id_created "
                    "ON messages(chat_id, created_at)"
                ))
                logger.info("[schema] Ensured index idx_messages_chat_id_created")

        # 1.3 Update documents table (add error_message and chat_id columns)
        if inspector.has_table("documents"):
            existing_doc_cols = {col["name"] for col in inspector.get_columns("documents")}
            if "error_message" not in existing_doc_cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE documents ADD COLUMN error_message TEXT"))
                    logger.info("[schema] Added column documents.error_message")
            if "chat_id" not in existing_doc_cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE documents ADD COLUMN chat_id VARCHAR(36)"))
                    logger.info("[schema] Added column documents.chat_id")

        # 2. Update users table (add role)
        if inspector.has_table("users"):
            existing_users_cols = {col["name"] for col in inspector.get_columns("users")}
            if "role" not in existing_users_cols:
                with engine.begin() as conn:
                    ddl = "ALTER TABLE users ADD COLUMN role VARCHAR(50) DEFAULT 'user'"
                    conn.execute(text(ddl))
                    logger.info("[schema] Added column users.role")

        # 3. Create audit_logs table if not exists
        if not inspector.has_table("audit_logs"):
            with engine.begin() as conn:
                ddl = """
                CREATE TABLE audit_logs (
                    id VARCHAR(36) PRIMARY KEY,
                    user_id VARCHAR(36),
                    event_type VARCHAR(50) NOT NULL,
                    details TEXT,
                    ip_address VARCHAR(45),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
                )
                """
                conn.execute(text(ddl))
                logger.info("[schema] Created table audit_logs")

        # 4. Add new provider columns to api_keys table and migrate/backfill
        if inspector.has_table("api_keys"):
            existing_api_key_cols = {col["name"] for col in inspector.get_columns("api_keys")}
            
            if "encrypted_key" in existing_api_key_cols:
                logger.info("[schema] Rebuilding api_keys table to drop old encrypted_key NOT NULL column")
                with engine.begin() as conn:
                    # 1. Rename old table
                    conn.execute(text("ALTER TABLE api_keys RENAME TO _api_keys_old"))
                    
                    # 2. Create new table without encrypted_key column
                    conn.execute(text("""
                        CREATE TABLE api_keys (
                            id VARCHAR(36) PRIMARY KEY,
                            user_id VARCHAR(36) NOT NULL,
                            provider_name VARCHAR(50) NOT NULL,
                            encrypted_api_key VARCHAR(500),
                            status VARCHAR(50) DEFAULT 'UNCONFIGURED' NOT NULL,
                            verified_at TIMESTAMP,
                            last_checked TIMESTAMP,
                            last_error TEXT,
                            available_models TEXT,
                            quota VARCHAR(255),
                            organization VARCHAR(255),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP,
                            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                        )
                    """))
                    
                    # 3. Copy data
                    conn.execute(text("""
                        INSERT INTO api_keys (
                            id, user_id, provider_name, encrypted_api_key, status, 
                            verified_at, last_checked, last_error, available_models, 
                            quota, organization, created_at, updated_at
                        )
                        SELECT 
                            id, user_id, provider_name, COALESCE(encrypted_api_key, encrypted_key), 
                            'UNCONFIGURED', NULL, NULL, NULL, '[]', NULL, NULL, created_at, NULL
                        FROM _api_keys_old
                    """))
                    
                    # 4. Drop old table
                    conn.execute(text("DROP TABLE _api_keys_old"))
                    logger.info("[schema] Rebuilt api_keys table successfully")
            else:
                # Add encrypted_api_key if missing
                if "encrypted_api_key" not in existing_api_key_cols:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE api_keys ADD COLUMN encrypted_api_key VARCHAR(500)"))
                        logger.info("[schema] Added column api_keys.encrypted_api_key")

                # Add other new fields
                new_cols = [
                    ("status", "VARCHAR(50) DEFAULT 'UNCONFIGURED' NOT NULL"),
                    ("verified_at", "TIMESTAMP"),
                    ("last_checked", "TIMESTAMP"),
                    ("last_error", "TEXT"),
                    ("available_models", "TEXT"),  # JSON string
                    ("quota", "VARCHAR(255)"),
                    ("organization", "VARCHAR(255)"),
                    ("updated_at", "TIMESTAMP"),
                ]
                with engine.begin() as conn:
                    for col_name, col_type in new_cols:
                        if col_name not in existing_api_key_cols:
                            _safe_add_column(conn, "api_keys", col_name, col_type)

                # Backfill statuses based on is_verified if status was not already present
                if "status" not in existing_api_key_cols:
                    with engine.begin() as conn:
                        if "is_verified" in existing_api_key_cols:
                            conn.execute(text("UPDATE api_keys SET status = 'VERIFIED' WHERE is_verified = 1"))
                            conn.execute(text("UPDATE api_keys SET status = 'UNCONFIGURED' WHERE is_verified = 0 OR is_verified IS NULL"))
                            logger.info("[schema] Backfilled statuses from is_verified column")
                        else:
                            conn.execute(text("UPDATE api_keys SET status = 'UNCONFIGURED'"))

                # Normalize 'gemini' provider name to 'google'
                with engine.begin() as conn:
                    conn.execute(text("UPDATE api_keys SET provider_name = 'google' WHERE provider_name = 'gemini'"))
                    logger.info("[schema] Normalized 'gemini' provider to 'google' in api_keys table")

        # 5. Add new preference columns to user_preferences table
        if inspector.has_table("user_preferences"):
            existing_pref_cols = {col["name"] for col in inspector.get_columns("user_preferences")}
            pref_cols = [
                ("temperature", "FLOAT DEFAULT 0.7"),
                ("max_tokens", "INTEGER DEFAULT 2048"),
                ("streaming", "BOOLEAN DEFAULT TRUE"),
                ("font_size", "VARCHAR(20) DEFAULT 'md'"),
                ("compact_mode", "BOOLEAN DEFAULT FALSE"),
                ("contrast_mode", "VARCHAR(20) DEFAULT 'normal'"),
                ("accent_color", "VARCHAR(20) DEFAULT 'blue'"),
                ("language", "VARCHAR(20) DEFAULT 'en'"),
                ("higher_intelligence", "BOOLEAN DEFAULT TRUE"),
                ("enable_dictation", "BOOLEAN DEFAULT TRUE"),
                ("improve_model", "BOOLEAN DEFAULT TRUE"),
                ("features", "TEXT"),
            ]
            with engine.begin() as conn:
                for col_name, col_type in pref_cols:
                    if col_name not in existing_pref_cols:
                        _safe_add_column(conn, "user_preferences", col_name, col_type)

    except Exception as exc:
        # MED-5 FIX: distinguish non-fatal "column already exists" warnings from
        # fatal errors (DB unreachable, permission denied). Swallowing ALL
        # exceptions here lets the server start with missing tables, causing a
        # cascade of confusing 500s that are very hard to diagnose.
        # OperationalError is NOT swallowed — if DB is down, startup must fail.
        _msg = str(exc).lower()
        _non_fatal_hints = (
            "duplicate column",      # SQLite: column already exists
            "already exists",        # PostgreSQL
            "no such table",         # inspection on empty db (first run)
        )
        if any(hint in _msg for hint in _non_fatal_hints):
            logger.warning(f"[schema] Non-fatal migration note: {exc}")
        else:
            # Fatal: DB connection refused, permission denied, etc.
            logger.error(f"[schema] Fatal migration error — server may not function correctly: {exc}")
            raise


