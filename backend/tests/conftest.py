from fastapi.testclient import TestClient

from app.core.config.settings import get_settings
from app.db.session.session import SessionLocal, init_db_engine
from app.main import app


def create_test_client() -> TestClient:
    settings = get_settings()
    init_db_engine(settings.database_url)

    # Create tables for test (SQLite in-memory)
    from app.db.base import Base
    from sqlalchemy import create_engine

    sync_engine = create_engine(settings.database_url.replace("+aiosqlite", "+pysqlite"))
    Base.metadata.create_all(bind=sync_engine)
    sync_engine.dispose()

    return TestClient(app)
