import pytest
import asyncio
import sys
from typing import AsyncGenerator

# ── Windows IOCP hang fix ─────────────────────────────────────────────────────
# Python 3.11+ on Windows defaults to ProactorEventLoop (IOCP). asyncio.wait_for
# and httpx.AsyncClient both leave dangling IOCP completion handles that prevent
# the per-test event loop from exiting, causing a 30 s hard timeout every time.
# Switching to SelectorEventLoop (POSIX-style poll) eliminates IOCP entirely and
# is fully compatible with aiosqlite, SQLAlchemy async, and anyio.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# ─────────────────────────────────────────────────────────────────────────────

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

import sys

@pytest.fixture(scope="session")
def event_loop():
    # Windows Python 3.11+ defaults to ProactorEventLoop (IOCP), which leaves
    # dangling completion handles after asyncio.wait_for / httpx calls in tests,
    # causing GetQueuedCompletionStatus to block indefinitely (30 s timeout fire).
    # Force SelectorEventLoop on Windows to avoid this entirely.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    async_session = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    async with async_session() as session:
        yield session
        await session.rollback()
        await session.close()

@pytest.fixture
async def override_get_db(db_session):
    async def _get_db():
        yield db_session
    return _get_db

@pytest.fixture(scope="session")
def anyio_backend():
    if sys.platform == "win32":
        # Pass loop_factory so anyio's asyncio backend always creates a
        # _WindowsSelectorEventLoop, bypassing any cached ProactorEventLoop policy.
        return ("asyncio", {"loop_factory": asyncio.SelectorEventLoop})
    return "asyncio"

@pytest.fixture(scope="session")
def event_loop_policy():
    """Override pytest-asyncio's built-in policy fixture to force SelectorEventLoop
    on Windows. pytest-asyncio 1.4 uses this fixture to create ALL per-test runners;
    returning WindowsSelectorEventLoopPolicy here guarantees no ProactorEventLoop
    (IOCP) is ever created, eliminating the 30 s GetQueuedCompletionStatus hang."""
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()

@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    yield
    app.dependency_overrides.clear()
