from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps.services import get_operations_service, get_storage_service
from app.main import app
from app.schemas.operations_automation import (
    ScalingPolicyListResponse,
    ScalingPolicySummary,
    ScheduledTaskListResponse,
    ScheduledTaskSummary,
    StoragePoolListResponse,
    StoragePoolSummary,
)
from tests.conftest import create_test_client


@pytest.fixture
def client() -> TestClient:
    return create_test_client()


def test_scaling_policy_crud(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.list_scaling_policies = AsyncMock(return_value=ScalingPolicyListResponse(items=[]))
    mock_svc.get_scaling_policy = AsyncMock(
        return_value=ScalingPolicySummary(id="sp-1", name="cpu-scale", metric_name="cpu_usage", threshold=80.0, comparison="gt", min_replicas=1, max_replicas=10, cooldown_seconds=300, target_resource_type="deployment", enabled=True)
    )
    mock_svc.create_scaling_policy = AsyncMock(
        return_value=ScalingPolicySummary(id="sp-1", name="cpu-scale", metric_name="cpu_usage", threshold=80.0, comparison="gt", min_replicas=1, max_replicas=10, cooldown_seconds=300, target_resource_type="deployment", enabled=True)
    )
    mock_svc.delete_scaling_policy = AsyncMock(return_value=None)
    app.dependency_overrides[get_operations_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/operations/scaling-policies")
        assert res.status_code == 200

        res = client.post("/api/v1/operations/scaling-policies", json={
            "name": "cpu-scale", "metric_name": "cpu_usage", "threshold": 80.0,
            "target_resource_type": "deployment",
        })
        assert res.status_code == 201
        assert res.json()["name"] == "cpu-scale"
        assert "operation_task_id" in res.json()

        res = client.get("/api/v1/operations/scaling-policies/sp-1")
        assert res.status_code == 200

        res = client.delete("/api/v1/operations/scaling-policies/sp-1")
        assert res.status_code == 204
    finally:
        app.dependency_overrides.clear()


def test_scheduled_task_crud(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.list_scheduled_tasks = AsyncMock(return_value=ScheduledTaskListResponse(items=[]))
    mock_svc.get_scheduled_task = AsyncMock(
        return_value=ScheduledTaskSummary(id="st-1", name="daily-backup", task_type="backup", cron_expression="0 3 * * *", target_action="create_snapshot", enabled=True)
    )
    mock_svc.create_scheduled_task = AsyncMock(
        return_value=ScheduledTaskSummary(id="st-1", name="daily-backup", task_type="backup", cron_expression="0 3 * * *", target_action="create_snapshot", enabled=True)
    )
    mock_svc.delete_scheduled_task = AsyncMock(return_value=None)
    app.dependency_overrides[get_operations_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/operations/scheduled-tasks")
        assert res.status_code == 200

        res = client.post("/api/v1/operations/scheduled-tasks", json={
            "name": "daily-backup", "task_type": "backup",
            "cron_expression": "0 3 * * *", "target_action": "create_snapshot",
        })
        assert res.status_code == 201
        assert res.json()["name"] == "daily-backup"

        res = client.get("/api/v1/operations/scheduled-tasks/st-1")
        assert res.status_code == 200

        res = client.delete("/api/v1/operations/scheduled-tasks/st-1")
        assert res.status_code == 204
    finally:
        app.dependency_overrides.clear()


def test_storage_pool_crud(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.list_pools = AsyncMock(return_value=StoragePoolListResponse(items=[]))
    mock_svc.get_pool = AsyncMock(
        return_value=StoragePoolSummary(id="pool-1", name="ceph-primary", pool_type="ceph", status="active", total_capacity_gb=10240, used_capacity_gb=3072, replication_factor=3)
    )
    mock_svc.create_pool = AsyncMock(
        return_value=StoragePoolSummary(id="pool-1", name="ceph-primary", pool_type="ceph", status="active", total_capacity_gb=10240, used_capacity_gb=0, replication_factor=3)
    )
    mock_svc.delete_pool = AsyncMock(return_value=None)
    app.dependency_overrides[get_storage_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/storage/pools")
        assert res.status_code == 200

        res = client.post("/api/v1/storage/pools", json={
            "name": "ceph-primary", "pool_type": "ceph", "total_capacity_gb": 10240,
        })
        assert res.status_code == 201
        data = res.json()
        assert data["name"] == "ceph-primary"
        assert data["pool_type"] == "ceph"
        assert "operation_task_id" in data

        res = client.get("/api/v1/storage/pools/pool-1")
        assert res.status_code == 200
        assert res.json()["name"] == "ceph-primary"

        res = client.delete("/api/v1/storage/pools/pool-1")
        assert res.status_code == 204
        assert res.headers.get("x-operation-task-id") is not None
    finally:
        app.dependency_overrides.clear()
