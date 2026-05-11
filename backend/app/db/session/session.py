"""Database engine lifecycle and session management.

Engine is created lazily inside the FastAPI lifespan (not at module level)
to avoid ``asyncpg`` event-loop conflicts with Gunicorn's ``preload_app=True``.

Usage::

    # In lifespan — creates the engine and binds the sessionmaker:
    init_db_engine(settings.database_url)

    # In any service (unchanged from SQLite era):
    from app.db.session.session import SessionLocal
    async with SessionLocal() as session:
        ...

    # FastAPI dependency injection:
    async def get_db():
        async with SessionLocal() as session:
            yield session

    # On shutdown:
    await dispose_engine()
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config.settings import get_settings

# ---------------------------------------------------------------------------
# Module-level sessionmaker — created without bind, configured in lifespan.
# All service files that ``from app.db.session.session import SessionLocal``
# continue to work because the *same object* is mutated via ``.configure()``.
# ---------------------------------------------------------------------------
SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    class_=AsyncSession,
    expire_on_commit=False,
)

_engine: Any = None  # async engine, set by init_db_engine()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def init_db_engine(database_url: str) -> None:
    """Create the async engine and bind the module-level sessionmaker.

    Call **once** per worker inside the FastAPI lifespan handler so that the
    engine is created *after* the Gunicorn fork, guaranteeing each worker
    has its own connection pool running on its own asyncio event loop.

    Parameters
    ----------
    database_url : str
        SQLAlchemy database URL (e.g. ``sqlite+aiosqlite:///...`` or
        ``postgresql+asyncpg://user:pass@host/db``).
    """
    global _engine
    settings = get_settings()

    pool_opts: dict[str, object] = {
        "future": True,
        "echo": settings.app_debug,
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 20,
        "pool_recycle": 3600,
        "pool_timeout": 30,
    }

    _engine = create_async_engine(database_url, **pool_opts)  # type: ignore[arg-type]
    SessionLocal.configure(bind=_engine)


async def dispose_engine() -> None:
    """Dispose the engine (called on shutdown)."""
    global _engine
    if _engine is not None:
        try:
            await _engine.dispose()
        except Exception:
            pass
        _engine = None


def get_engine() -> Any:
    """Return the current engine instance (for low-level use)."""
    if _engine is None:
        raise RuntimeError("Engine not initialised — call init_db_engine() first")
    return _engine


# ---------------------------------------------------------------------------
# FastAPI dependency — yields an async session per request
# ---------------------------------------------------------------------------


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
