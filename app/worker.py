from typing import Any
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config.settings import get_settings
from app.modules.migration.manager import MigrationManager
from app.clients.openstack.connection import OpenStackConnectionFactory
from app.clients.vmware.connection import VMwareClientFactory

async def execute_vmware_migration_task(ctx: dict[str, Any], task_id: str, vm_name: str, target_flavor: str, target_network: str) -> None:
    settings = get_settings()
    vmware_factory = VMwareClientFactory(settings)
    os_factory = OpenStackConnectionFactory(settings)
    manager = MigrationManager(vmware_factory, os_factory)
    
    await manager.execute_vmware_migration(
        task_id=task_id,
        vm_name=vm_name,
        target_flavor=target_flavor,
        target_network=target_network,
    )

async def startup(ctx: dict[str, Any]) -> None:
    pass

async def shutdown(ctx: dict[str, Any]) -> None:
    pass

settings = get_settings()
redis_settings = RedisSettings.from_dsn(settings.redis_url)

class WorkerSettings:
    functions = [execute_vmware_migration_task]
    redis_settings = redis_settings
    on_startup = startup
    on_shutdown = shutdown

async def get_redis_pool() -> Any:
    return await create_pool(redis_settings)
