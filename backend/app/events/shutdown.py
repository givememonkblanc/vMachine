from app.db.session.session import dispose_engine


async def on_shutdown() -> None:
    """애플리케이션 종료 시 실행되는 정리 로직"""
    await dispose_engine()
