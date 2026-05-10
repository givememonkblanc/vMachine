import pytest
from unittest.mock import MagicMock
from app.services.openstack.volume_service import VolumeService
from app.schemas.volume import VolumeCreateRequest
from app.clients.openstack.connection import OpenStackConnectionFactory


@pytest.fixture
def mock_openstack_factory():
    factory = MagicMock(spec=OpenStackConnectionFactory)
    conn = MagicMock()
    factory.create.return_value = conn
    return factory, conn


def test_list_volumes(mock_openstack_factory):
    factory, conn = mock_openstack_factory
    volume_service = VolumeService(factory)

    mock_vol = MagicMock()
    mock_vol.id = "vol-1"
    mock_vol.name = "data-volume"
    mock_vol.status = "available"
    mock_vol.size = 100
    mock_vol.bootable = "false"
    
    conn.block_storage.volumes.return_value = [mock_vol]

    result = volume_service.list_volumes()

    assert len(result) == 1
    assert result[0].id == "vol-1"
    assert result[0].size == 100


def test_create_volume(mock_openstack_factory):
    factory, conn = mock_openstack_factory
    volume_service = VolumeService(factory)

    mock_vol = MagicMock()
    mock_vol.id = "new-vol"
    mock_vol.name = "new-data-vol"
    mock_vol.status = "creating"
    mock_vol.size = 50
    mock_vol.bootable = "false"
    
    conn.block_storage.create_volume.return_value = mock_vol

    payload = VolumeCreateRequest(
        name="new-data-vol",
        size=50,
        description="test volume"
    )

    result = volume_service.create_volume(payload)

    assert result.id == "new-vol"
    assert result.size == 50
    conn.block_storage.create_volume.assert_called_once_with(
        name="new-data-vol",
        size=50,
        description="test volume"
    )
