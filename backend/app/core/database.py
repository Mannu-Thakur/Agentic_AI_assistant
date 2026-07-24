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
    )


def _build_async_engine():
    url = settings.ASYNC_DATABASE_URL
    if _is_sqlite(url):
        return create_async_engine(
            url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False, "timeout": 30},
        )
    return create_async_engine(
        url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


# ── Synchronous Engine & Session Maker (Alembic / sync utilities) ─────────────
engine = _build_sync_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── Asynchronous Engine & Session Maker (application route handlers) ──────────
async_engine = _build_async_engine()
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ── SQLite PRAGMA configuration for WAL mode (for sync and async) ─────────────
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if _is_sqlite(settings.DATABASE_URL):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

@event.listens_for(async_engine.sync_engine, "connect")
def set_async_sqlite_pragma(dbapi_connection, connection_record):
    if _is_sqlite(settings.DATABASE_URL):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

Base = declarative_base()


# ── FastAPI dependency ─────────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Phase 3: safe schema migrations ───────────────────────────────────────────

def run_schema_migrations() -> None:
    """
    Safely perform database schema upgrades:
    1. Add expires_at, project_id, session_id, and confidence to memories table if missing.
    2. Add role column to users table if missing.
    3. Create audit_logs table if it does not exist.
    4. Add is_verified column to api_keys table if missing, backfill existing rows to True.

    Uses database-agnostic SQLAlchemy inspection.
    Only called explicitly from the application lifespan — NOT on module import.
    """
    from sqlalchemy import inspect

    try:
        inspector = inspect(engine)

        # 1. Update memories table
        if inspector.has_table("memories"):
            existing_memories_cols = {col["name"] for col in inspector.get_columns("memories")}
            new_memories_cols = [
                ("expires_at",  "DATETIME"),
                ("project_id",  "VARCHAR(128)"),
                ("session_id",  "VARCHAR(128)"),
                ("confidence",  "FLOAT DEFAULT 1.0"),
            ]
            with engine.begin() as conn:
                for col_name, col_type in new_memories_cols:
                    if col_name not in existing_memories_cols:
                        ddl = f"ALTER TABLE memories ADD COLUMN {col_name} {col_type}"
                        conn.execute(text(ddl))
                        logger.info(f"[schema] Added column memories.{col_name}")

        # 1.1 Update chats table (add is_live_share)
        if inspector.has_table("chats"):
            existing_chats_cols = {col["name"] for col in inspector.get_columns("chats")}
            if "is_live_share" not in existing_chats_cols:
                with engine.begin() as conn:
                    ddl = "ALTER TABLE chats ADD COLUMN is_live_share BOOLEAN DEFAULT FALSE"
                    conn.execute(text(ddl))
                    logger.info("[schema] Added column chats.is_live_share")

        # 1.2 Update messages table (add images JSON column)
        if inspector.has_table("messages"):
            existing_msg_cols = {col["name"] for col in inspector.get_columns("messages")}
            if "images" not in existing_msg_cols:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE messages ADD COLUMN images TEXT"))
                    logger.info("[schema] Added column messages.images")

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
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
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
                            verified_at DATETIME,
                            last_checked DATETIME,
                            last_error TEXT,
                            available_models TEXT,
                            quota VARCHAR(255),
                            organization VARCHAR(255),
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            updated_at DATETIME,
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
                    ("verified_at", "DATETIME"),
                    ("last_checked", "DATETIME"),
                    ("last_error", "TEXT"),
                    ("available_models", "TEXT"),  # JSON string
                    ("quota", "VARCHAR(255)"),
                    ("organization", "VARCHAR(255)"),
                    ("updated_at", "DATETIME"),
                ]
                with engine.begin() as conn:
                    for col_name, col_type in new_cols:
                        if col_name not in existing_api_key_cols:
                            conn.execute(text(f"ALTER TABLE api_keys ADD COLUMN {col_name} {col_type}"))
                            logger.info(f"[schema] Added column api_keys.{col_name}")

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

    except Exception as exc:
        logger.warning(f"[schema] Migration warning: {exc}")
