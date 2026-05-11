import pytest
from unittest.mock import MagicMock
from app.services.openstack.network_service import NetworkService
from app.schemas.openstack.network import NetworkCreateRequest
from app.clients.openstack.connection import OpenStackConnectionFactory


@pytest.fixture
def mock_openstack_factory():
    factory = MagicMock(spec=OpenStackConnectionFactory)
    conn = MagicMock()
    factory.create.return_value = conn
    return factory, conn


def test_list_networks(mock_openstack_factory):
    factory, conn = mock_openstack_factory
    network_service = NetworkService(factory)

    # Mock network data
    mock_net = MagicMock()
    mock_net.id = "net-1"
    mock_net.name = "public-net"
    mock_net.status = "ACTIVE"
    mock_net.subnets = ["subnet-1"]
    mock_net.admin_state_up = True
    mock_net.shared = False
    mock_net.is_router_external = True
    
    conn.network.networks.return_value = [mock_net]

    result = network_service.list_networks()

    assert len(result) == 1
    assert result[0].id == "net-1"
    assert result[0].name == "public-net"
    assert result[0].subnets == ["subnet-1"]


def test_create_network(mock_openstack_factory):
    factory, conn = mock_openstack_factory
    network_service = NetworkService(factory)

    conn.network.find_network.return_value = None  # No existing network

    # Mock create network
    mock_net = MagicMock()
    mock_net.id = "new-net-id"
    conn.network.create_network.return_value = mock_net

    # Mock create subnet
    mock_subnet = MagicMock()
    mock_subnet.id = "new-subnet-id"
    conn.network.create_subnet.return_value = mock_subnet

    payload = NetworkCreateRequest(
        name="my-net",
        cidr="192.168.1.0/24",
        ip_version=4
    )

    result = network_service.create_network(payload)

    assert result.network_id == "new-net-id"
    assert result.subnet_id == "new-subnet-id"
    assert result.name == "my-net"
    conn.network.create_network.assert_called_once_with(
        name="my-net", shared=False, admin_state_up=True
    )
    conn.network.create_subnet.assert_called_once()
