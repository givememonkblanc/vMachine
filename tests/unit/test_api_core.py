from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps.services import get_auth_service
from app.main import app
from app.schemas.auth import (
    OpenStackServiceCatalogResponse,
    OpenStackServiceEndpoint,
    OpenStackTokenInfo,
    OpenStackValidationResponse,
)
from tests.conftest import create_test_client


@pytest.fixture
def client() -> TestClient:
    return create_test_client()


def test_auth_config(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.get_token_info.return_value = OpenStackTokenInfo(
        configured=True, auth_url="http://auth", region_name="RegionOne"
    )
    app.dependency_overrides[get_auth_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/auth/config")
        assert res.status_code == 200
        assert res.json()["configured"] is True
    finally:
        app.dependency_overrides.clear()


def test_auth_validate_and_session(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_response = OpenStackValidationResponse(
        connected=True,
        region_name="RegionOne",
        project_name="admin",
        user_name="admin",
        interface="public",
    )
    mock_svc.validate_connection.return_value = mock_response
    app.dependency_overrides[get_auth_service] = lambda: mock_svc

    try:
        res1 = client.post("/api/v1/auth/validate")
        assert res1.status_code == 200
        assert res1.json()["connected"] is True

        res2 = client.get("/api/v1/auth/session")
        assert res2.status_code == 200
        assert res2.json()["user_name"] == "admin"
    finally:
        app.dependency_overrides.clear()


def test_auth_endpoints(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.get_service_catalog.return_value = OpenStackServiceCatalogResponse(
        items=[OpenStackServiceEndpoint(service_type="compute", url="http://compute")]
    )
    app.dependency_overrides[get_auth_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/auth/endpoints")
        assert res.status_code == 200
        assert len(res.json()["items"]) == 1
    finally:
        app.dependency_overrides.clear()
