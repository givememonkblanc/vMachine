from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.core.config.settings import get_settings

settings = get_settings()

# Pool settings — default 5 connections, max 20 overflow.
# SQLite's aiosqlite driver ignores pool_size/max_overflow, but these take
# effect when switching to PostgreSQL / MySQL in production.
_db_pool_opts: dict[str, object] = {
    "future": True,
    "echo": settings.app_debug,
    "pool_pre_ping": True,
    "pool_size": 5,
    "max_overflow": 20,
    "pool_recycle": 3600,   # recycle connections every hour
    "pool_timeout": 30,     # seconds to wait for a pool connection
}

engine = create_async_engine(settings.database_url, **_db_pool_opts)  # type: ignore[arg-type]
sync_engine = create_engine(
    settings.database_url.replace("+aiosqlite", "+pysqlite"),
    future=True,
    echo=settings.app_debug,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=20,
    pool_recycle=3600,
)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def init_db_sync() -> None:
    Base.metadata.create_all(bind=sync_engine)
