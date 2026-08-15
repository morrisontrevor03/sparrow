"""
Shared fixtures for the test suite.

Environment variables must be set before any app module is imported, because
pydantic-settings reads them at class definition time.

Event-loop discipline: asyncpg connections are bound to the loop that opened
them, and pytest-asyncio does not guarantee that session-scoped fixtures and
function-scoped tests share a loop. So there is no module-level engine here —
each fixture builds its own with NullPool and disposes it. That costs a
connection per test and buys immunity from "attached to a different loop" and
"another operation is in progress", which is a trade worth making.
"""
import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# ── env setup (must precede all app imports) ─────────────────────────────────
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://ci:ci@localhost:5432/sparrow_ci")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("BACKEND_URL", "http://localhost:8000")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3000")

# ── app imports (after env) ──────────────────────────────────────────────────
from app.database import Base, get_db  # noqa: E402
from app.dependencies import create_access_token, hash_password  # noqa: E402
from app.models.campaign import Campaign  # noqa: E402
from app.models.credits import CreditLedgerEntry  # noqa: E402
from app.models.subscription import BillingAccount  # noqa: E402
from app.models.user import User, UserPreferences  # noqa: E402

_TEST_DB_URL = os.environ["DATABASE_URL"]


def _make_engine():
    return create_async_engine(_TEST_DB_URL, echo=False, poolclass=NullPool)


@pytest_asyncio.fixture(autouse=True)
async def _schema() -> AsyncGenerator[None, None]:
    """
    Ensure the schema exists and start each test from an empty users table.

    create_all is a no-op once the tables are there, so running it per test is
    cheap and removes any ordering dependency between tests.
    """
    engine = _make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Everything of consequence cascades from users; oauth_clients is the
        # one table with no user FK.
        await conn.execute(text("DELETE FROM users"))
        await conn.execute(text("DELETE FROM oauth_clients"))
    await engine.dispose()

    yield


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    engine = _make_engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX client wired to the test DB, with outbound side effects mocked."""
    from app.main import app

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = _override_db

    mock_scheduler = MagicMock()
    mock_scheduler.start = MagicMock()
    mock_scheduler.shutdown = MagicMock()

    with (
        patch("app.routers.auth.send_email", new_callable=AsyncMock, return_value=True),
        patch("app.main.init_posthog"),
        patch("app.main.shutdown_posthog"),
        patch("app.main.register_jobs"),
        patch("app.main.scheduler", mock_scheduler),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    """An active, verified user with a starting credit balance."""
    u = User(
        email="test@example.com",
        hashed_password=hash_password("password123"),
        full_name="Test User",
        is_verified=True,
        is_active=True,
    )
    db.add(u)
    await db.flush()
    db.add(UserPreferences(user_id=u.id))
    db.add(BillingAccount(user_id=u.id))
    db.add(CreditLedgerEntry(user_id=u.id, delta=100, reason="signup_grant"))
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def broke_user(db: AsyncSession) -> User:
    """A user with a zero balance, for the out-of-credits paths."""
    u = User(
        email="broke@example.com",
        hashed_password=hash_password("password123"),
        full_name="Broke User",
        is_verified=True,
        is_active=True,
    )
    db.add(u)
    await db.flush()
    db.add(UserPreferences(user_id=u.id))
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def campaign(db: AsyncSession, user: User) -> Campaign:
    c = Campaign(
        user_id=user.id,
        name="Test campaign",
        campaign_type="business_development",
        objective="Sell widgets to widget buyers",
        target_titles=["VP of Engineering"],
        target_companies=["Acme"],
        status="active",
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@pytest_asyncio.fixture
def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest_asyncio.fixture
def broke_auth_headers(broke_user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(broke_user.id)}"}
