from app.db.session.session import dispose_engine


async def on_shutdown() -> None:
    await dispose_engine()
