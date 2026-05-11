from sqlalchemy import text

from app.common.utils.openstack_cache import configure_from_settings
from app.core.config.settings import get_settings
from app.core.logging.logger import configure_logging
from app.db.session.session import SessionLocal, get_engine


async def on_startup() -> None:
    """애플리케이션 시작 시 실행되는 초기화 로직"""
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_from_settings()

    # Health-check: verify the database is reachable.
    # Table creation is handled by Alembic migrations, not the application.
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning("Database health check failed (non-blocking): %s", exc)
