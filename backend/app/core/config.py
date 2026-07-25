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
import logging
from typing import List, Optional
from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    """Search well-known Windows paths for tesseract.exe."""
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours — prevents unexpected session logouts
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30       # 30 days rolling refresh
    ALGORITHM: str = "HS256"
    
    JWT_ISSUER: str = "flagship-auth"
    JWT_AUDIENCE: str = "flagship-app"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
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
    ALLOWED_REDIRECT_URIS: List[str] = [
        "http://localhost:5173/auth/google/callback",
        "http://localhost:5173/auth/github/callback",
        "http://127.0.0.1:5173/auth/google/callback",
        "http://127.0.0.1:5173/auth/github/callback",
    ]

    # Database
    DATABASE_URL: str = "sqlite:///./sql_app.db"

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql+psycopg2://"):
            return url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
        elif url.startswith("sqlite://"):
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

    # Search API
    TAVILY_API_KEY: Optional[str] = None

    # Vector DB
    VECTOR_DB_DIR: str = "./vector_db"

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
    UPLOAD_DIR: str = "./uploads"

    # OCR — Tesseract binary path (auto-detected if blank)
    TESSERACT_CMD: Optional[str] = None
    REQUIRE_OCR: bool = False
    
    # Malware scan (ClamAV integration)
    CLAMAV_HOST: Optional[str] = None
    CLAMAV_PORT: int = 3310

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _post_init(self) -> "Settings":
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
