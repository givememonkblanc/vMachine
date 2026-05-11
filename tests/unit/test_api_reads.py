from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps.services import (
    get_compute_service,
    get_flavor_service,
    get_image_service,
    get_keypair_service,
    get_network_service,
    get_router_service,
    get_security_group_service,
    get_tenant_service,
    get_volume_service,
)
from app.main import app
from app.schemas.identity.tenant import ProjectSummary
from app.schemas.openstack.compute import ServerDetail, ServerSummary
from app.schemas.openstack.flavor import FlavorSummary
from app.schemas.openstack.image import ImageSummary
from app.schemas.openstack.keypair import KeypairSummary
from app.schemas.openstack.network import NetworkDetail, NetworkSummary, SubnetSummary
from app.schemas.openstack.router import RouterSummary
from app.schemas.openstack.security_group import (
    SecurityGroupDetail,
    SecurityGroupSummary,
)
from app.schemas.openstack.volume import VolumeSummary
from tests.conftest import create_test_client


@pytest.fixture
def client() -> TestClient:
    return create_test_client()


def test_list_and_get_compute(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.list_servers.return_value = [ServerSummary(id="server-1", name="test-vm")]
    mock_svc.get_server.return_value = ServerDetail(
        id="server-1", name="test-vm", updated="now"
    )
    app.dependency_overrides[get_compute_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/compute/servers")
        assert res.status_code == 200
        assert len(res.json()["items"]) == 1

        res = client.get("/api/v1/compute/servers/server-1")
        assert res.status_code == 200
        assert res.json()["updated"] == "now"
    finally:
        app.dependency_overrides.clear()


def test_list_and_get_network(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.list_networks.return_value = [NetworkSummary(id="net-1", name="test-net")]
    mock_svc.get_network.return_value = NetworkDetail(
        id="net-1", name="test-net", subnet_details=[SubnetSummary(id="sub-1")]
    )
    app.dependency_overrides[get_network_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/networks")
        assert res.status_code == 200
        assert len(res.json()["items"]) == 1

        res = client.get("/api/v1/networks/net-1")
        assert res.status_code == 200
        assert len(res.json()["subnet_details"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_list_and_get_security_group(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.list_security_groups.return_value = [
        SecurityGroupSummary(id="sg-1", name="test-sg")
    ]
    mock_svc.get_security_group.return_value = SecurityGroupDetail(
        id="sg-1", name="test-sg"
    )
    app.dependency_overrides[get_security_group_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/security-groups")
        assert res.status_code == 200
        assert len(res.json()["items"]) == 1

        res = client.get("/api/v1/security-groups/sg-1")
        assert res.status_code == 200
        assert res.json()["name"] == "test-sg"
    finally:
        app.dependency_overrides.clear()


def test_list_volumes(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.list_volumes.return_value = [VolumeSummary(id="vol-1", name="test-vol")]
    app.dependency_overrides[get_volume_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/volumes")
        assert res.status_code == 200
        assert len(res.json()["items"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_list_routers(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.list_routers.return_value = [
        RouterSummary(id="router-1", name="test-router")
    ]
    app.dependency_overrides[get_router_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/routers")
        assert res.status_code == 200
        assert len(res.json()["items"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_list_keypairs(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.list_keypairs.return_value = [
        KeypairSummary(name="test-key", public_key="pub")
    ]
    app.dependency_overrides[get_keypair_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/keypairs")
        assert res.status_code == 200
        assert len(res.json()["items"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_list_images(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.list_images.return_value = [ImageSummary(id="img-1", name="ubuntu")]
    app.dependency_overrides[get_image_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/images")
        assert res.status_code == 200
        assert len(res.json()["items"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_list_flavors(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.list_flavors.return_value = [
        FlavorSummary(id="flv-1", name="m1.small", vcpus=1)
    ]
    app.dependency_overrides[get_flavor_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/flavors")
        assert res.status_code == 200
        assert len(res.json()["items"]) == 1
    finally:
        app.dependency_overrides.clear()


def test_list_tenants(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.list_projects.return_value = [ProjectSummary(id="proj-1", name="admin")]
    app.dependency_overrides[get_tenant_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/tenants/projects")
        assert res.status_code == 200
        assert len(res.json()["items"]) == 1
    finally:
        app.dependency_overrides.clear()
