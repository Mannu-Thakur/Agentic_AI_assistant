"""
app/core/config.py — Application settings.

Production hardening:
  • SECRET_KEY validator: raises on startup if using the default insecure key
    in non-development environments.
  • TESSERACT_CMD: auto-configure common Windows install paths so OCR works
    without manually editing code.
  • Explicit ENVIRONMENT field (development | staging | production).
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import List, Optional, Any, Union
from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.core.storage_paths import resolve_storage_path

logger = logging.getLogger("app.core.config")

_DEFAULT_SECRET_KEY = "supersecretkeychangeinproduction1234567890"

# Common Tesseract install locations on Windows
_TESSERACT_SEARCH_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Users\{username}\AppData\Local\Programs\Tesseract-OCR\tesseract.exe",
    r"C:\tools\tesseract\tesseract.exe",
]


def _find_tesseract() -> Optional[str]:
    """Search system PATH and well-known Windows paths for tesseract binary."""
    import shutil
    system_path = shutil.which("tesseract")
    if system_path:
        return system_path
    for path in _TESSERACT_SEARCH_PATHS:
        resolved = path.format(username=os.environ.get("USERNAME", ""))
        if os.path.isfile(resolved):
            return resolved
    return None


class Settings(BaseSettings):
    PROJECT_NAME: str = "Flagship Agentic AI Workspace"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"  # development | staging | production

    # Security & JWT
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    # Extended access token expiry (7 days) prevents early logouts during active sessions.
    # Refresh tokens remain valid for 30 days.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days (10080 minutes)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30       # 30 days rolling refresh
    ALGORITHM: str = "HS256"

    @field_validator("ALGORITHM")
    @classmethod
    def _validate_algorithm(cls, v: str) -> str:
        # L-7 FIX: Only allow safe, widely-supported JWT algorithms.
        allowed = {"HS256", "HS384", "HS512", "RS256", "ES256"}
        if v not in allowed:
            raise ValueError(f"ALGORITHM must be one of {allowed}, got {v!r}")
        return v

    JWT_ISSUER: str = "flagship-auth"
    JWT_AUDIENCE: str = "flagship-app"

    # Cookie Configuration
    COOKIE_SAMESITE: str = "lax"  # "lax" for same-domain/proxy, "none" for cross-origin credentials


    # CORS
    BACKEND_CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://127.0.0.1:3000",
    ]
    
    # Whitelisted OAuth Callback Redirect URIs to prevent Open Redirects
    ALLOWED_REDIRECT_URIS: Union[List[str], str] = [
        "http://localhost:5173/auth/google/callback",
        "http://localhost:5173/auth/github/callback",
        "http://127.0.0.1:5173/auth/google/callback",
        "http://127.0.0.1:5173/auth/github/callback",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", "ALLOWED_REDIRECT_URIS", mode="before")
    @classmethod
    def _parse_origins_list(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    # Database
    # ── PRODUCTION NOTE ────────────────────────────────────────────────────────
    # SQLite is acceptable ONLY for ENVIRONMENT=development.
    # For staging / production set DATABASE_URL to a PostgreSQL connection string:
    #
    #   DATABASE_URL=postgresql://user:password@localhost:5432/dbname
    #   DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/dbname
    #
    # The server will refuse to start if SQLite is configured in staging/production.
    DATABASE_URL: str = "sqlite:///./sql_app.db"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _canonicalize_database_url(cls, v: Any) -> str:
        if isinstance(v, str) and v.startswith("sqlite:///") and not v.startswith("sqlite:////"):
            rel_part = v[len("sqlite:///"):]
            if not os.path.isabs(rel_part):
                backend_dir = Path(__file__).resolve().parent.parent.parent
                abs_db_path = (backend_dir / rel_part).resolve()
                return f"sqlite:///{abs_db_path.as_posix()}"
        return v

    @field_validator("VECTOR_DB_DIR", "UPLOAD_DIR", "ARTIFACT_DIR", mode="before")
    @classmethod
    def _canonicalize_storage_paths(cls, v: Any) -> str:
        if isinstance(v, str) and not os.path.isabs(v):
            backend_dir = Path(__file__).resolve().parent.parent.parent
            return str((backend_dir / v).resolve())
        return v

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        url = self.DATABASE_URL
        # Normalize postgres:// shorthand first
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        # M-7 FIX: Guard against double-replacement when the URL is already asyncpg.
        if url.startswith("postgresql+asyncpg://"):
            return url  # already correct — don't replace again
        if url.startswith("postgresql+psycopg2://"):
            return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("sqlite://"):
            return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
        return url


    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # LLM Providers
    GROQ_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_API_BASE: Optional[str] = None
    # Model identifiers are deployment configuration, not hard-coded business
    # logic.  Defaults are current supported fallback candidates, but a staging
    # deployment must still validate its own account/model access at startup.
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENROUTER_MODEL: str = "openrouter/auto"
    # Optional per-model input/output USD prices for telemetry. Keep this
    # deployment-owned because provider prices and enterprise discounts vary.
    PRICING_OVERRIDE_JSON: str = ""

    # Remote integrations and isolated code execution.  Keep code execution
    # disabled unless a separate hardened sandbox service is explicitly wired.
    ALLOW_INSECURE_MCP_IN_DEVELOPMENT: bool = False
    ENABLE_ADMIN_DATABASE_INSPECTOR: bool = False
    # These integrations inspect deployment-host state or create long-running
    # background work.  They are deliberately opt-in in a public deployment.
    ENABLE_GIT_INTEGRATION: bool = False
    ENABLE_MISSION_MODE: bool = True
    MISSION_MAX_QUEUE_SIZE: int = 50
    ENABLE_CODE_EXECUTION: bool = False
    CODE_SANDBOX_URL: Optional[str] = None
    SANDBOX_SHARED_SECRET: Optional[str] = None
    CODE_SANDBOX_TIMEOUT_SECONDS: float = 8.0

    # Search Providers
    TAVILY_API_KEY:  Optional[str] = None   # tavily.com — AI-curated search
    SERP_API_KEY:    Optional[str] = None   # serpapi.com — real Google results
    EXA_API_KEY:     Optional[str] = None   # exa.ai    — neural semantic search

    # Web search routing (comma-separated priority order)
    WEB_SEARCH_PROVIDER_ORDER: str = "tavily,serpapi,exa,duckduckgo"
    WEB_SEARCH_MAX_RESULTS:    int = 8      # max results to fetch per search

    # Vector DB
    VECTOR_DB_DIR: str = "./vector_db"   # deployment-specific; falls back if unwritable

    # OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:5173/auth/google/callback"
    GITHUB_REDIRECT_URI: str = "http://localhost:5173/auth/github/callback"
    ENABLE_MOCK_OAUTH: bool = False

    # File upload constraints
    MAX_UPLOAD_SIZE_MB: int = 20
    UPLOAD_DIR: str = "./uploads"         # deployment-specific; falls back if unwritable
    # Generated agent files use a separate, persistent, per-user store.
    ARTIFACT_DIR: str = "./artifacts"     # deployment-specific; falls back if unwritable
    MAX_ARTIFACT_SIZE_MB: int = 20

    # OCR — Tesseract binary path (auto-detected if blank)
    TESSERACT_CMD: Optional[str] = None
    REQUIRE_OCR: bool = False
    
    # Malware scan (ClamAV integration)
    CLAMAV_HOST: Optional[str] = None
    CLAMAV_PORT: int = 3310

    # Email / SMTP (leave blank to use console-mode dev fallback)
    # NOTE: For Gmail SMTP, SMTP_FROM_EMAIL must match SMTP_USER (your Gmail address).
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None  # Defaults to SMTP_USER if blank
    SMTP_FROM_NAME: str = "openChat Workspace"

    # Frontend URL — used to build password reset links sent in emails
    FRONTEND_URL: str = "http://localhost:5173"

    # Password reset token lifetime (minutes)
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 15

    # Knowledge Graph — Neo4j
    NEO4J_URI: Optional[str] = None
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: Optional[str] = None
    NEO4J_DATABASE: str = "neo4j"
    GRAPHRAG_ENABLED: bool = False
    GRAPHRAG_MAX_GRAPH_RESULTS: int = 10

    # Business Domain Mode
    # One of: "claims" | "warranty" | "fraud" | "enterprise" | None (generic)
    # When set, injects domain-specific context into agent system prompts.
    DOMAIN_MODE: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _post_init(self) -> "Settings":
        # Render's native Python runtime cannot write to the Docker image's
        # conventional /app path. Keep usable configured directories and fall
        # back to the runtime temp directory when a stale path is unwritable.
        for setting_name, storage_name in (
            ("VECTOR_DB_DIR", "vector_db"),
            ("UPLOAD_DIR", "uploads"),
            ("ARTIFACT_DIR", "artifacts"),
        ):
            setattr(
                self,
                setting_name,
                resolve_storage_path(getattr(self, setting_name), storage_name),
            )

        # ── Database engine enforcement ─────────────────────────────────────
        # SQLite cannot handle concurrent writes from multiple async workers.
        # In staging and production environments we require PostgreSQL.
        _db_url = self.DATABASE_URL.lower()
        _is_sqlite = _db_url.startswith("sqlite")
        if _is_sqlite and self.ENVIRONMENT in ("staging", "production"):
            logger.critical(
                "FATAL: SQLite is configured as the database in a "
                f"{self.ENVIRONMENT} environment. SQLite cannot handle concurrent "
                "writes from multiple async workers and will cause data corruption "
                "and request failures under load. "
                "Set DATABASE_URL to a PostgreSQL connection string in your .env file "
                "(e.g. postgresql://user:pass@localhost:5432/yourdb) and restart."
            )
            sys.exit(1)
        elif _is_sqlite and self.ENVIRONMENT == "development":
            logger.warning(
                "[DB] Using SQLite in development mode. "
                "Set DATABASE_URL=postgresql://... in .env for staging/production."
            )

        # ── Secret key hardening ────────────────────────────────────────────
        if self.SECRET_KEY == _DEFAULT_SECRET_KEY:
            if self.ENVIRONMENT in ("staging", "production"):
                logger.critical(
                    "FATAL: SECRET_KEY is set to the insecure default value in a "
                    f"{self.ENVIRONMENT} environment. Set a strong random SECRET_KEY "
                    "in your .env file and restart the server."
                )
                sys.exit(1)
            else:
                logger.warning(
                    "SECRET_KEY is using the insecure default value. "
                    "Set a strong random SECRET_KEY in .env before deploying."
                )

        if self.ENABLE_CODE_EXECUTION:
            if not self.CODE_SANDBOX_URL or not self.SANDBOX_SHARED_SECRET:
                if self.ENVIRONMENT in ("staging", "production"):
                    raise ValueError(
                        "ENABLE_CODE_EXECUTION requires CODE_SANDBOX_URL and "
                        "SANDBOX_SHARED_SECRET outside development."
                    )
                logger.warning(
                    "[Sandbox] Code execution is enabled but the isolated sandbox "
                    "is not fully configured; execution will fail closed."
                )

        # ── Tesseract auto-detection & requirement enforcement ───────────────
        if not self.TESSERACT_CMD:
            found = _find_tesseract()
            if found:
                self.TESSERACT_CMD = found
                logger.info(f"[OCR] Tesseract auto-detected at: {found}")
                try:
                    import pytesseract
                    pytesseract.pytesseract.tesseract_cmd = found
                except ImportError:
                    pass
            elif self.REQUIRE_OCR:
                logger.critical(
                    "FATAL: OCR is required (REQUIRE_OCR=True) but Tesseract OCR binary "
                    "was not found on this system. Install Tesseract-OCR and restart the server."
                )
                sys.exit(1)
            else:
                logger.warning(
                    "[OCR] Tesseract binary not found. OCR on scanned images/PDFs will "
                    "be unavailable. Install Tesseract-OCR and set TESSERACT_CMD in .env."
                )
        else:
            # Apply user-configured path
            if not os.path.isfile(self.TESSERACT_CMD):
                if self.REQUIRE_OCR or self.ENVIRONMENT in ("staging", "production"):
                    logger.critical(
                        f"FATAL: Configured TESSERACT_CMD path '{self.TESSERACT_CMD}' "
                        "does not exist or is not a file."
                    )
                    sys.exit(1)
                else:
                    logger.warning(
                        f"Configured TESSERACT_CMD path '{self.TESSERACT_CMD}' "
                        "does not exist. OCR fallback will fail."
                    )
            else:
                try:
                    import pytesseract
                    pytesseract.pytesseract.tesseract_cmd = self.TESSERACT_CMD
                except ImportError:
                    pass

        return self


settings = Settings()
