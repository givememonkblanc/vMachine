import os

from sqlalchemy import select

from app.clients.openstack.connection import OpenStackConnectionFactory
from app.clients.vmware.connection import VMwareClientFactory
from app.common.exceptions.base import AppException
from app.core.config.settings import get_settings
from app.db.session.session import SessionLocal
from app.models.migration_task import MigrationTask


class MigrationManager:
    def __init__(
        self,
        vmware_factory: VMwareClientFactory,
        os_factory: OpenStackConnectionFactory,
    ):
        self.vmware_factory = vmware_factory
        self.os_factory = os_factory
        self._disk_dir: str = get_settings().migration_disk_dir

    async def execute_vmware_migration(
        self, task_id: str, vm_name: str, target_flavor: str, target_network: str
    ) -> None:
        async with SessionLocal() as session:
            stmt = select(MigrationTask).where(MigrationTask.id == task_id)
            result = await session.execute(stmt)
            task = result.scalar_one_or_none()

            if not task:
                return

            try:
                task.status = "in_progress"
                task.progress = 10
                await session.commit()

                # 1. Connect to VMware & Get VM
                vmware_vm = self.vmware_factory.get_vm_by_name(vm_name)
                task.progress = 30
                await session.commit()

                # 2. Export Disk (configurable directory)
                os.makedirs(self._disk_dir, exist_ok=True)
                exported_disk_path = self.vmware_factory.export_vm_disk(
                    vmware_vm, self._disk_dir
                )
                task.progress = 50
                await session.commit()

                # 3. Upload to OpenStack Glance (streaming — avoids loading
                #    the entire disk file into memory at once).
                with open(exported_disk_path, "rb") as _disk_file:
                    image = self.os_factory.call(
                        "image",
                        "create_image",
                        name=f"migrated-{vm_name}",
                        data=_disk_file,
                        disk_format="vmdk",
                        container_format="bare",
                    )
                task.progress = 70
                await session.commit()

                # 4. Create OpenStack Server (use get_* instead of find_*)
                flavor = self.os_factory.call("compute", "get_flavor", target_flavor)
                if not flavor:
                    raise AppException(
                        f"Target flavor '{target_flavor}' not found in OpenStack"
                    )

                network = self.os_factory.call("network", "get_network", target_network)
                if not network:
                    raise AppException(
                        f"Target network '{target_network}' not found in OpenStack"
                    )

                server = self.os_factory.call(
                    "compute",
                    "create_server",
                    name=f"migrated-{vm_name}",
                    image_id=image.id,
                    flavor_id=flavor.id,
                    networks=[{"uuid": network.id}],
                )

                task.progress = 100
                task.status = "completed"
                task.destination_ref = server.id
                await session.commit()

            except Exception as exc:
                task.status = "failed"
                task.progress = 0
                await session.commit()
                raise AppException(f"Migration failed: {exc}")
