import pytest
from unittest.mock import MagicMock
from app.services.compute_service import ComputeService
from app.schemas.compute import ServerCreateRequest
from app.clients.openstack.connection import OpenStackConnectionFactory


@pytest.fixture
def mock_openstack_factory():
    factory = MagicMock(spec=OpenStackConnectionFactory)
    conn = MagicMock()
    factory.create.return_value = conn
    return factory, conn


def test_list_servers(mock_openstack_factory):
    factory, conn = mock_openstack_factory
    compute_service = ComputeService(factory)

    # Mock server data
    mock_server = MagicMock()
    mock_server.id = "server-1"
    mock_server.name = "test-server"
    mock_server.status = "ACTIVE"
    mock_server.created = "2024-01-01T00:00:00Z"
    mock_server.key_name = "test-key"
    mock_server.project_id = "project-1"
    mock_server.availability_zone = "nova"
    mock_server.flavor = {"id": "flavor-1"}
    mock_server.image = {"id": "image-1"}
    mock_server.addresses = {"public": [{"addr": "1.2.3.4"}]}
    
    conn.compute.servers.return_value = [mock_server]

    # Execute
    result = compute_service.list_servers()

    # Assert
    assert len(result) == 1
    assert result[0].id == "server-1"
    assert result[0].name == "test-server"
    assert result[0].status == "ACTIVE"
    assert result[0].flavor_id == "flavor-1"
    assert result[0].image_id == "image-1"
    assert "public" in result[0].addresses
    assert result[0].addresses["public"] == ["1.2.3.4"]


def test_create_server(mock_openstack_factory):
    factory, conn = mock_openstack_factory
    compute_service = ComputeService(factory)

    # Mock dependencies
    conn.image.find_image.return_value = MagicMock(id="image-1")
    conn.compute.find_flavor.return_value = MagicMock(id="flavor-1")
    conn.network.find_network.return_value = MagicMock(id="net-1")
    conn.compute.find_keypair.return_value = MagicMock(id="key-1")

    # Mock created server
    mock_server = MagicMock()
    mock_server.id = "server-new"
    mock_server.name = "new-server"
    mock_server.status = "BUILD"
    mock_server.created = "2024-01-01T00:00:00Z"
    mock_server.key_name = "test-key"
    mock_server.project_id = "project-1"
    mock_server.availability_zone = "nova"
    conn.compute.create_server.return_value = mock_server

    payload = ServerCreateRequest(
        name="new-server",
        image_id="image-1",
        flavor_id="flavor-1",
        network_id="net-1",
        key_name="test-key"
    )

    result = compute_service.create_server(payload)

    assert result.id == "server-new"
    assert result.name == "new-server"
    conn.compute.create_server.assert_called_once()
