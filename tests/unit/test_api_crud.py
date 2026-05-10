from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps.services import (
    get_compute_service,
    get_flavor_service,
    get_image_service,
    get_keypair_service,
    get_kubernetes_service,
    get_network_service,
    get_router_service,
    get_security_group_service,
    get_tenant_service,
    get_volume_service,
)
from app.main import app
from app.schemas.openstack.compute import ServerActionResponse, ServerSummary
from app.schemas.openstack.flavor import FlavorSummary
from app.schemas.openstack.image import ImageSummary
from app.schemas.openstack.keypair import KeypairCreateResponse
from app.schemas.openstack.network import NetworkCreateResponse
from app.schemas.openstack.router import RouterCreateResponse
from app.schemas.openstack.security_group import SecurityGroupCreateResponse, SecurityGroupRuleCreateResponse
from app.schemas.identity.tenant import ProjectSummary
from app.schemas.openstack.volume import VolumeSummary
from tests.conftest import create_test_client


@pytest.fixture
def client() -> TestClient:
    return create_test_client()


def test_keypair_crud(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.create_keypair.return_value = KeypairCreateResponse(
        name="test-key", public_key="pub", private_key="priv"
    )
    mock_svc.delete_keypair.return_value = None
    app.dependency_overrides[get_keypair_service] = lambda: mock_svc

    try:
        res = client.post("/api/v1/keypairs", json={"name": "test-key"})
        assert res.status_code == 201
        assert res.json()["name"] == "test-key"
        assert "operation_task_id" in res.json()
        res = client.delete("/api/v1/keypairs/test-key")
        assert res.status_code == 204
        assert res.headers.get("x-operation-task-id") is not None
    finally:
        app.dependency_overrides.clear()


def test_volume_crud(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.create_volume.return_value = VolumeSummary(id="vol-1", name="test-vol", size=10)
    mock_svc.delete_volume.return_value = None
    app.dependency_overrides[get_volume_service] = lambda: mock_svc

    try:
        res = client.post("/api/v1/volumes", json={"name": "test-vol", "size": 10})
        assert res.status_code == 201
        assert res.json()["id"] == "vol-1"
        assert "operation_task_id" in res.json()
        res = client.delete("/api/v1/volumes/vol-1")
        assert res.status_code == 204
        assert res.headers.get("x-operation-task-id") is not None
    finally:
        app.dependency_overrides.clear()


def test_network_crud(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.create_network.return_value = NetworkCreateResponse(
        network_id="net-1", subnet_id="sub-1", name="test-net"
    )
    mock_svc.delete_network.return_value = None
    app.dependency_overrides[get_network_service] = lambda: mock_svc

    try:
        res = client.post("/api/v1/networks", json={"name": "test-net", "cidr": "10.0.0.0/24"})
        assert res.status_code == 201
        assert res.json()["network_id"] == "net-1"
        assert "operation_task_id" in res.json()
        res = client.delete("/api/v1/networks/net-1")
        assert res.status_code == 204
        assert res.headers.get("x-operation-task-id") is not None
    finally:
        app.dependency_overrides.clear()


def test_router_crud(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.create_router.return_value = RouterCreateResponse(router_id="router-1", name="test-router")
    mock_svc.delete_router.return_value = None
    mock_svc.add_interface.return_value = None
    mock_svc.remove_interface.return_value = None
    app.dependency_overrides[get_router_service] = lambda: mock_svc

    try:
        res = client.post("/api/v1/routers", json={"name": "test-router"})
        assert res.status_code == 201
        assert res.json()["router_id"] == "router-1"
        assert "operation_task_id" in res.json()
        res = client.post("/api/v1/routers/router-1/interfaces", json={"subnet_id": "sub-1"})
        assert res.status_code == 204
        assert res.headers.get("x-operation-task-id") is not None
        res = client.delete("/api/v1/routers/router-1/interfaces/sub-1")
        assert res.status_code == 204
        assert res.headers.get("x-operation-task-id") is not None
        res = client.delete("/api/v1/routers/router-1")
        assert res.status_code == 204
        assert res.headers.get("x-operation-task-id") is not None
    finally:
        app.dependency_overrides.clear()


def test_security_group_crud(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.create_security_group.return_value = SecurityGroupCreateResponse(
        security_group_id="sg-1", name="test-sg"
    )
    mock_svc.delete_security_group.return_value = None
    mock_svc.create_rule.return_value = SecurityGroupRuleCreateResponse(rule_id="rule-1")
    mock_svc.delete_rule.return_value = None
    app.dependency_overrides[get_security_group_service] = lambda: mock_svc

    try:
        res = client.post("/api/v1/security-groups", json={"name": "test-sg"})
        assert res.status_code == 201
        assert res.json()["security_group_id"] == "sg-1"
        assert "operation_task_id" in res.json()
        res = client.post("/api/v1/security-groups/sg-1/rules", json={"direction": "ingress"})
        assert res.status_code == 201
        assert res.json()["rule_id"] == "rule-1"
        res = client.delete("/api/v1/security-groups/rules/rule-1")
        assert res.status_code == 204
        res = client.delete("/api/v1/security-groups/sg-1")
        assert res.status_code == 204
    finally:
        app.dependency_overrides.clear()


def test_compute_crud(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.create_server.return_value = ServerSummary(id="vm-1", name="test-vm")
    mock_svc.perform_action.return_value = ServerActionResponse(server_id="vm-1", action="start", accepted=True)
    mock_svc.delete_server.return_value = None
    mock_svc.attach_volume.return_value = None
    mock_svc.detach_volume.return_value = None
    app.dependency_overrides[get_compute_service] = lambda: mock_svc

    try:
        payload = {
            "name": "test-vm",
            "image_id": "img-1",
            "flavor_id": "flv-1",
            "network_id": "net-1"
        }
        res = client.post("/api/v1/compute/servers", json=payload)
        assert res.status_code == 201
        assert res.json()["id"] == "vm-1"
        assert "operation_task_id" in res.json()
        res = client.post("/api/v1/compute/servers/vm-1/actions", json={"action": "start"})
        assert res.status_code == 200
        assert res.json()["accepted"] is True
        res = client.post("/api/v1/compute/servers/vm-1/volumes", json={"volume_id": "vol-1"})
        assert res.status_code == 204
        res = client.delete("/api/v1/compute/servers/vm-1/volumes/vol-1")
        assert res.status_code == 204
        res = client.delete("/api/v1/compute/servers/vm-1")
        assert res.status_code == 204
    finally:
        app.dependency_overrides.clear()


def test_compute_resize_and_snapshot(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.resize_server.return_value = None
    mock_svc.confirm_resize.return_value = None
    mock_svc.revert_resize.return_value = None
    mock_svc.create_server_image.return_value = "img-snapshot-1"
    app.dependency_overrides[get_compute_service] = lambda: mock_svc

    try:
        res = client.post("/api/v1/compute/servers/vm-1/resize", json={"flavor_id": "flv-2"})
        assert res.status_code == 202
        assert res.headers.get("x-operation-task-id") is not None

        res = client.post("/api/v1/compute/servers/vm-1/resize/action", json={"action": "confirm"})
        assert res.status_code == 200
        assert res.json()["status"] == "confirm"
        assert "operation_task_id" in res.json()

        res = client.post("/api/v1/compute/servers/vm-1/resize/action", json={"action": "revert"})
        assert res.status_code == 200
        assert res.json()["status"] == "revert"
        assert "operation_task_id" in res.json()

        res = client.post("/api/v1/compute/servers/vm-1/snapshots", json={"name": "test-snapshot"})
        assert res.status_code == 201
        data = res.json()
        assert data["server_id"] == "vm-1"
        assert data["image_name"] == "test-snapshot"
        assert "operation_task_id" in data
    finally:
        app.dependency_overrides.clear()


def test_flavor_crud(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.create_flavor.return_value = FlavorSummary(id="flv-1", name="test-flavor", vcpus=2, ram=4096, disk=20)
    mock_svc.get_flavor.return_value = FlavorSummary(id="flv-1", name="test-flavor", vcpus=2, ram=4096, disk=20)
    mock_svc.delete_flavor.return_value = None
    app.dependency_overrides[get_flavor_service] = lambda: mock_svc

    try:
        res = client.post("/api/v1/flavors", json={"name": "test-flavor", "vcpus": 2, "ram": 4096, "disk": 20})
        assert res.status_code == 201
        assert res.json()["id"] == "flv-1"
        assert "operation_task_id" in res.json()

        res = client.get("/api/v1/flavors/flv-1")
        assert res.status_code == 200
        assert res.json()["id"] == "flv-1"

        res = client.delete("/api/v1/flavors/flv-1")
        assert res.status_code == 204
        assert res.headers.get("x-operation-task-id") is not None
    finally:
        app.dependency_overrides.clear()


def test_image_crud(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.create_image.return_value = ImageSummary(id="img-1", name="test-image")
    mock_svc.get_image.return_value = ImageSummary(id="img-1", name="test-image")
    mock_svc.delete_image.return_value = None
    app.dependency_overrides[get_image_service] = lambda: mock_svc

    try:
        res = client.post(
            "/api/v1/images",
            json={"name": "test-image", "container_format": "bare", "disk_format": "qcow2"},
        )
        assert res.status_code == 201
        assert res.json()["id"] == "img-1"
        assert "operation_task_id" in res.json()

        res = client.get("/api/v1/images/img-1")
        assert res.status_code == 200
        assert res.json()["id"] == "img-1"

        res = client.delete("/api/v1/images/img-1")
        assert res.status_code == 204
        assert res.headers.get("x-operation-task-id") is not None
    finally:
        app.dependency_overrides.clear()


def test_tenant_crud(client: TestClient) -> None:
    mock_svc = MagicMock()
    mock_svc.create_project.return_value = ProjectSummary(id="proj-1", name="test-project")
    mock_svc.get_project.return_value = ProjectSummary(id="proj-1", name="test-project")
    mock_svc.delete_project.return_value = None
    app.dependency_overrides[get_tenant_service] = lambda: mock_svc

    try:
        res = client.post("/api/v1/tenants/projects", json={"name": "test-project"})
        assert res.status_code == 201
        assert res.json()["id"] == "proj-1"
        assert "operation_task_id" in res.json()

        res = client.get("/api/v1/tenants/projects/proj-1")
        assert res.status_code == 200
        assert res.json()["id"] == "proj-1"

        res = client.delete("/api/v1/tenants/projects/proj-1")
        assert res.status_code == 204
        assert res.headers.get("x-operation-task-id") is not None
    finally:
        app.dependency_overrides.clear()


def test_kubernetes_crud(client: TestClient) -> None:
    from app.schemas.kubernetes.kubernetes import (
        DeploymentSummary,
        K8sClusterInfo,
        PodSummary,
        ServiceSummary,
    )

    mock_svc = MagicMock()
    mock_svc.list_pods.return_value = {"items": []}
    mock_svc.get_pod.return_value = PodSummary(name="test-pod", namespace="default", status="Running")
    mock_svc.create_pod.return_value = PodSummary(name="test-pod", namespace="default", status="Running")
    mock_svc.delete_pod.return_value = None
    mock_svc.list_deployments.return_value = {"items": []}
    mock_svc.get_deployment.return_value = DeploymentSummary(name="test-dep", namespace="default", replicas=1, ready_replicas=1, available_replicas=1)
    mock_svc.create_deployment.return_value = DeploymentSummary(name="test-dep", namespace="default", replicas=1, ready_replicas=0, available_replicas=0)
    mock_svc.delete_deployment.return_value = None
    mock_svc.scale_deployment.return_value = DeploymentSummary(name="test-dep", namespace="default", replicas=3, ready_replicas=3, available_replicas=3)
    mock_svc.list_services.return_value = {"items": []}
    mock_svc.get_service.return_value = ServiceSummary(name="test-svc", namespace="default", type="ClusterIP")
    mock_svc.create_service.return_value = ServiceSummary(name="test-svc", namespace="default", type="ClusterIP", cluster_ip="10.0.0.1")
    mock_svc.delete_service.return_value = None
    mock_svc.get_cluster_info.return_value = K8sClusterInfo(node_count=2, namespaces=["default", "kube-system"], version="1.28")
    app.dependency_overrides[get_kubernetes_service] = lambda: mock_svc

    try:
        res = client.get("/api/v1/k8s/pods")
        assert res.status_code == 200

        res = client.get("/api/v1/k8s/pods/test-pod")
        assert res.status_code == 200
        assert res.json()["name"] == "test-pod"

        res = client.post("/api/v1/k8s/pods", json={"name": "test-pod", "image": "nginx:latest"})
        assert res.status_code == 201
        assert res.json()["name"] == "test-pod"
        assert "operation_task_id" in res.json()

        res = client.delete("/api/v1/k8s/pods/test-pod")
        assert res.status_code == 204
        assert res.headers.get("x-operation-task-id") is not None

        res = client.get("/api/v1/k8s/deployments")
        assert res.status_code == 200

        res = client.get("/api/v1/k8s/deployments/test-dep")
        assert res.status_code == 200

        res = client.post("/api/v1/k8s/deployments", json={"name": "test-dep", "image": "nginx:latest"})
        assert res.status_code == 201
        assert res.json()["name"] == "test-dep"
        assert "operation_task_id" in res.json()

        res = client.patch("/api/v1/k8s/deployments/test-dep/scale", json={"replicas": 3})
        assert res.status_code == 200
        assert res.json()["replicas"] == 3

        res = client.delete("/api/v1/k8s/deployments/test-dep")
        assert res.status_code == 204
        assert res.headers.get("x-operation-task-id") is not None

        res = client.get("/api/v1/k8s/services")
        assert res.status_code == 200

        res = client.get("/api/v1/k8s/services/test-svc")
        assert res.status_code == 200

        res = client.post("/api/v1/k8s/services", json={"name": "test-svc", "port": 80})
        assert res.status_code == 201
        assert res.json()["name"] == "test-svc"
        assert "operation_task_id" in res.json()

        res = client.delete("/api/v1/k8s/services/test-svc")
        assert res.status_code == 204
        assert res.headers.get("x-operation-task-id") is not None

        res = client.get("/api/v1/k8s/cluster")
        assert res.status_code == 200
        data = res.json()
        assert data["node_count"] == 2
        assert "default" in data["namespaces"]
    finally:
        app.dependency_overrides.clear()
