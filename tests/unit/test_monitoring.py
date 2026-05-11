from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps.services import get_monitoring_service
from app.main import app
from app.schemas.monitoring.monitoring import (
    AlertListResponse,
    AlertRecordSummary,
    DashboardSummary,
    HypervisorUsage,
    MetricListResponse,
    ProjectUsage,
)
from tests.conftest import create_test_client


@pytest.fixture
def client() -> TestClient:
    return create_test_client()


@pytest.fixture
def mock_svc() -> MagicMock:
    svc = MagicMock(
        spec=[
            "query_metrics",
            "get_latest_metrics",
            "get_hypervisor_usage",
            "get_project_usage",
            "list_alerts",
            "resolve_alert",
            "get_dashboard_summary",
            "record_metric",
        ]
    )
    svc.query_metrics = AsyncMock(return_value=MetricListResponse(items=[]))
    svc.get_latest_metrics = AsyncMock(return_value=MetricListResponse(items=[]))
    svc.get_hypervisor_usage = AsyncMock(return_value=[])
    svc.get_project_usage = AsyncMock(return_value=[])
    svc.list_alerts = AsyncMock(return_value=AlertListResponse(items=[]))
    svc.resolve_alert = AsyncMock(
        return_value=AlertRecordSummary(
            id="alert-1",
            severity="warning",
            title="Test Alert",
            source="test",
            status="resolved",
        )
    )
    svc.get_dashboard_summary = AsyncMock(
        return_value=DashboardSummary(
            total_instances=5,
            active_instances=3,
            total_hypervisors=2,
            total_networks=3,
            total_volumes=4,
            active_alerts=1,
            total_storage_gb=100,
            used_storage_gb=40,
        )
    )
    svc.record_metric = AsyncMock(return_value=None)
    return svc


def test_query_metrics(client: TestClient, mock_svc: MagicMock) -> None:
    app.dependency_overrides[get_monitoring_service] = lambda: mock_svc
    try:
        res = client.get("/api/v1/monitoring/metrics")
        assert res.status_code == 200
        assert res.json() == {"items": []}
    finally:
        app.dependency_overrides.clear()


def test_get_latest_metrics(client: TestClient, mock_svc: MagicMock) -> None:
    app.dependency_overrides[get_monitoring_service] = lambda: mock_svc
    try:
        res = client.get("/api/v1/monitoring/metrics/latest")
        assert res.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_get_hypervisor_usage(client: TestClient, mock_svc: MagicMock) -> None:
    mock_svc.get_hypervisor_usage = AsyncMock(
        return_value=[
            HypervisorUsage(
                hypervisor="hv-1",
                cpu_usage=45.0,
                memory_usage=60.0,
                memory_total_mb=65536,
                memory_used_mb=39321,
                disk_usage=50.0,
                running_vms=3,
            )
        ]
    )
    app.dependency_overrides[get_monitoring_service] = lambda: mock_svc
    try:
        res = client.get("/api/v1/monitoring/hypervisors")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["hypervisor"] == "hv-1"
        assert data[0]["cpu_usage"] == 45.0
    finally:
        app.dependency_overrides.clear()


def test_get_project_usage(client: TestClient, mock_svc: MagicMock) -> None:
    mock_svc.get_project_usage = AsyncMock(
        return_value=[
            ProjectUsage(
                project_id="proj-1",
                instance_count=3,
                total_vcpus=6,
                total_ram_mb=8192,
                total_disk_gb=100,
            )
        ]
    )
    app.dependency_overrides[get_monitoring_service] = lambda: mock_svc
    try:
        res = client.get("/api/v1/monitoring/projects")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["project_id"] == "proj-1"
        assert data[0]["instance_count"] == 3
    finally:
        app.dependency_overrides.clear()


def test_list_alerts(client: TestClient, mock_svc: MagicMock) -> None:
    app.dependency_overrides[get_monitoring_service] = lambda: mock_svc
    try:
        res = client.get("/api/v1/monitoring/alerts")
        assert res.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_resolve_alert(client: TestClient, mock_svc: MagicMock) -> None:
    app.dependency_overrides[get_monitoring_service] = lambda: mock_svc
    try:
        res = client.post("/api/v1/monitoring/alerts/alert-1/resolve")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == "alert-1"
        assert data["status"] == "resolved"
    finally:
        app.dependency_overrides.clear()


def test_get_dashboard(client: TestClient, mock_svc: MagicMock) -> None:
    app.dependency_overrides[get_monitoring_service] = lambda: mock_svc
    try:
        res = client.get("/api/v1/monitoring/dashboard")
        assert res.status_code == 200
        data = res.json()
        assert data["total_instances"] == 5
        assert data["active_alerts"] == 1
    finally:
        app.dependency_overrides.clear()
