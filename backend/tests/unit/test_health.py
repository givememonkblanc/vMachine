from typing import cast

from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = cast(dict[str, object], response.json())
    assert body["status"] == "ok"
    assert "service" in body
