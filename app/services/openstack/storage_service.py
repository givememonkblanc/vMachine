from sqlalchemy import select

from app.common.exceptions.base import AppException
from app.db.session.session import SessionLocal
from app.models.storage_pool import StoragePool
from app.schemas.orchestration.operations_automation import (
    StoragePoolCreateRequest,
    StoragePoolListResponse,
    StoragePoolSummary,
)


class StorageService:
    async def list_pools(self) -> StoragePoolListResponse:
        async with SessionLocal() as session:
            result = await session.execute(
                select(StoragePool).order_by(StoragePool.created_at.desc())
            )
            items = [self._serialize(p) for p in result.scalars().all()]
        return StoragePoolListResponse(items=items)

    async def get_pool(self, pool_id: str) -> StoragePoolSummary:
        async with SessionLocal() as session:
            pool = await session.get(StoragePool, pool_id)
            if not pool:
                raise AppException(message="Storage pool not found", status_code=404, error_code="storage_pool_not_found")
            return self._serialize(pool)

    async def create_pool(self, payload: StoragePoolCreateRequest) -> StoragePoolSummary:
        async with SessionLocal() as session:
            pool = StoragePool(
                name=payload.name,
                description=payload.description,
                pool_type=payload.pool_type,
                total_capacity_gb=payload.total_capacity_gb,
                replication_factor=payload.replication_factor,
            )
            session.add(pool)
            await session.commit()
            await session.refresh(pool)
            return self._serialize(pool)

    async def delete_pool(self, pool_id: str) -> None:
        async with SessionLocal() as session:
            pool = await session.get(StoragePool, pool_id)
            if not pool:
                raise AppException(message="Storage pool not found", status_code=404, error_code="storage_pool_not_found")
            await session.delete(pool)
            await session.commit()

    @staticmethod
    def _serialize(p: StoragePool) -> StoragePoolSummary:
        return StoragePoolSummary(
            id=p.id,
            name=p.name,
            pool_type=p.pool_type,
            status=p.status,
            total_capacity_gb=p.total_capacity_gb,
            used_capacity_gb=p.used_capacity_gb,
            replication_factor=p.replication_factor,
            created_at=p.created_at.isoformat() if p.created_at else None,
        )
