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


async def health_check_task(ctx: dict[str, Any]) -> dict[str, Any]:
    """Periodic health check — returns service status."""
    return {"status": "ok"}


async def cleanup_stale_migrations_task(ctx: dict[str, Any]) -> None:
    """Mark migrations stuck in 'in_progress' for > 1 hour as failed."""
    from datetime import datetime, timedelta, timezone
    from app.db.session.session import SessionLocal
    from app.models.migration_task import MigrationTask
    from sqlalchemy import select

    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    async with SessionLocal() as session:
        stmt = (
            select(MigrationTask)
            .where(MigrationTask.status == "in_progress")
            .where(MigrationTask.created_at < cutoff)
        )
        result = await session.execute(stmt)
        stale = result.scalars().all()
        for task in stale:
            task.status = "failed"
            task.progress = 0
        await session.commit()


async def startup(ctx: dict[str, Any]) -> None:
    pass


async def shutdown(ctx: dict[str, Any]) -> None:
    pass


settings = get_settings()
redis_settings = RedisSettings.from_dsn(settings.redis_url)


class WorkerSettings:
    functions = [execute_vmware_migration_task, health_check_task, cleanup_stale_migrations_task]
    redis_settings = redis_settings
    on_startup = startup
    on_shutdown = shutdown
    keep_result = 300        # keep results for 5 minutes
    keep_result_failed = 600  # keep failed results for 10 minutes
    max_burst_jobs = 10      # max concurrency


async def get_redis_pool() -> Any:
    return await create_pool(redis_settings)
