from app.clients.openstack.connection import OpenStackConnectionFactory
from app.clients.vmware.connection import VMwareClientFactory
from app.common.exceptions.base import AppException
from app.db.session.session import SessionLocal
from app.models.migration_task import MigrationTask
from sqlalchemy import select


class MigrationManager:
    def __init__(self, vmware_factory: VMwareClientFactory, os_factory: OpenStackConnectionFactory):
        self.vmware_factory = vmware_factory
        self.os_factory = os_factory

    async def execute_vmware_migration(self, task_id: str, vm_name: str, target_flavor: str, target_network: str) -> None:
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

                # 2. Export Disk
                exported_disk_path = self.vmware_factory.export_vm_disk(vmware_vm, "/tmp/migrations")
                task.progress = 50
                await session.commit()

                # 3. Upload to OpenStack Glance
                conn = self.os_factory.create()
                image = conn.image.create_image(
                    name=f"migrated-{vm_name}",
                    filename=exported_disk_path,
                    disk_format="vmdk",
                    container_format="bare",
                )
                task.progress = 70
                await session.commit()

                # 4. Create OpenStack Server
                flavor = conn.compute.find_flavor(target_flavor, ignore_missing=True)
                if not flavor:
                    raise AppException(f"Target flavor '{target_flavor}' not found in OpenStack")

                network = conn.network.find_network(target_network, ignore_missing=True)
                if not network:
                    raise AppException(f"Target network '{target_network}' not found in OpenStack")

                server = conn.compute.create_server(
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
