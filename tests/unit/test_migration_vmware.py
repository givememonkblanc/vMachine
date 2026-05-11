from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from app.clients.openstack.connection import OpenStackConnectionFactory
from app.clients.vmware.connection import VMwareClientFactory
from app.models.migration_task import MigrationTask
from app.modules.migration.manager import MigrationManager


@pytest.mark.asyncio
async def test_execute_vmware_migration():
    vmware_factory = MagicMock(spec=VMwareClientFactory)
    os_factory = MagicMock(spec=OpenStackConnectionFactory)

    # Setup VMware mocks
    vm_mock = MagicMock()
    vm_mock.name = "test-vm"
    vmware_factory.get_vm_by_name.return_value = vm_mock
    vmware_factory.export_vm_disk.return_value = "/tmp/migrations/test-vm.vmdk"

    # Setup OpenStack mocks
    conn_mock = MagicMock()
    os_factory.create.return_value = conn_mock

    image_mock = MagicMock(id="image-123")
    conn_mock.image.create_image.return_value = image_mock

    flavor_mock = MagicMock(id="flavor-123")
    conn_mock.compute.get_flavor.return_value = flavor_mock

    network_mock = MagicMock(id="net-123")
    conn_mock.network.get_network.return_value = network_mock

    server_mock = MagicMock(id="server-123")
    conn_mock.compute.create_server.return_value = server_mock

    manager = MigrationManager(vmware_factory, os_factory)

    # Mock Database Session
    mock_session = AsyncMock()
    mock_task = MigrationTask(id="task-123", status="queued", progress=0)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_task
    mock_session.execute.return_value = mock_result

    with (
        patch("app.modules.migration.manager.SessionLocal", return_value=mock_session),
        patch("builtins.open", mock_open(read_data=b"fake-disk-content")),
    ):
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None

        await manager.execute_vmware_migration(
            task_id="task-123",
            vm_name="test-vm",
            target_flavor="m1.small",
            target_network="public",
        )

    # Verify state changes
    assert mock_task.status == "completed"
    assert mock_task.progress == 100
    assert mock_task.destination_ref == "server-123"

    # Verify VMware calls
    vmware_factory.get_vm_by_name.assert_called_once_with("test-vm")
    vmware_factory.export_vm_disk.assert_called_once_with(vm_mock, "/tmp/migrations")

    # Verify OpenStack calls — data is a file-like object (streaming)
    call_kwargs = conn_mock.image.create_image.call_args[1]
    assert call_kwargs["name"] == "migrated-test-vm"
    assert call_kwargs["disk_format"] == "vmdk"
    assert call_kwargs["container_format"] == "bare"
    assert hasattr(call_kwargs["data"], "read")  # file-like object

    conn_mock.compute.create_server.assert_called_once_with(
        name="migrated-test-vm",
        image_id="image-123",
        flavor_id="flavor-123",
        networks=[{"uuid": "net-123"}],
    )
