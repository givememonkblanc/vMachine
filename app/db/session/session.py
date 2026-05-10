from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.core.config.settings import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, future=True, echo=settings.app_debug, pool_pre_ping=True)
sync_engine = create_engine(settings.database_url.replace("+aiosqlite", "+pysqlite"), future=True, echo=settings.app_debug)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def init_db_sync() -> None:
    Base.metadata.create_all(bind=sync_engine)
