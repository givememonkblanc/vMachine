from fastapi.testclient import TestClient

from app.db.session import session as db_session
from app.main import app


def create_test_client() -> TestClient:
    db_session.init_db_sync()
    return TestClient(app)
