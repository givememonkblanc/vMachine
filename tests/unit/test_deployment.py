from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps.services import get_cluster_service, get_migration_service
from app.main import app
from app.schemas.deployment import (
    BatchDeployResponse,
    ClusterListResponse,
    ClusterSummary,
    MigrationListResponse,
    MigrationTaskSummary,
)
from tests.conftest import create_test_client


@pytest.fixture
def client() -> TestClient:
    return create_test_client()


def test_cluster_crud(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.list_clusters = AsyncMock(return_value=ClusterListResponse(items=[]))
    mock_svc.get_cluster = AsyncMock(
        return_value=ClusterSummary(id="cluster-1", name="test-cluster", cluster_type="compute", status="active", node_count=0)
    )
    mock_svc.create_cluster = AsyncMock(
        return_value=ClusterSummary(id="cluster-1", name="test-cluster", cluster_type="compute", status="active", node_count=2)
    )
    mock_svc.delete_cluster = AsyncMock(return_value=None)
    mock_svc.batch_deploy = AsyncMock(
        return_value=BatchDeployResponse(template_name="test", requested=3, created=3)
    )
    app.dependency_overrides[get_cluster_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/clusters")
        assert res.status_code == 200

        res = client.post("/api/v1/clusters", json={"name": "test-cluster", "node_count": 2})
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "test-cluster"
        assert "operation_task_id" in data

        res = client.get("/api/v1/clusters/cluster-1")
        assert res.status_code == 200
        assert res.json()["name"] == "test-cluster"

        res = client.post("/api/v1/clusters/cluster-1/deploy", json={
            "template_name": "web", "instance_count": 3,
            "image_id": "img-1", "flavor_id": "flv-1", "network_id": "net-1",
        })
        assert res.status_code == 200
        assert res.json()["created"] == 3

        res = client.delete("/api/v1/clusters/cluster-1")
        assert res.status_code == 204
        assert res.headers.get("x-operation-task-id") is not None
    finally:
        app.dependency_overrides.clear()


def test_migration_crud(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.list_migrations = AsyncMock(return_value=MigrationListResponse(items=[]))
    mock_svc.get_migration = AsyncMock(
        return_value=MigrationTaskSummary(id="mig-1", migration_type="cold", source_ref="vm-1", resource_type="server", status="queued", progress=0)
    )
    mock_svc.create_migration = AsyncMock(
        return_value=MigrationTaskSummary(id="mig-1", migration_type="cold", source_ref="vm-1", resource_type="server", status="queued", progress=0)
    )
    mock_svc.update_migration_progress = AsyncMock(
        return_value=MigrationTaskSummary(id="mig-1", migration_type="cold", source_ref="vm-1", resource_type="server", status="running", progress=50)
    )
    app.dependency_overrides[get_migration_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/migrations")
        assert res.status_code == 200

        res = client.post("/api/v1/migrations", json={
            "migration_type": "cold", "source_ref": "vm-1",
        })
        assert res.status_code == 201
        data = res.json()
        assert data["migration_type"] == "cold"
        assert data["source_ref"] == "vm-1"
        assert "operation_task_id" in data

        res = client.get("/api/v1/migrations/mig-1")
        assert res.status_code == 200
        assert res.json()["status"] == "queued"

        res = client.post("/api/v1/migrations/mig-1/progress?progress=50")
        assert res.status_code == 200
        assert res.json()["progress"] == 50
    finally:
        app.dependency_overrides.clear()
