from app.db.session.session import engine


async def on_shutdown() -> None:
    """애플리케이션 종료 시 실행되는 정리 로직"""
    try:
        await engine.dispose()
    except Exception as exc:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning("Engine dispose failed (non-blocking): %s", exc)
