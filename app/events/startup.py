from app.common.utils.openstack_cache import configure_from_settings
from app.core.config.settings import get_settings
from app.core.logging.logger import configure_logging
from app.db.session.session import init_db


async def on_startup() -> None:
    """애플리케이션 시작 시 실행되는 초기화 로직"""
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_from_settings()
    try:
        await init_db()
    except Exception as exc:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning("Database initialization failed (non-blocking): %s", exc)
