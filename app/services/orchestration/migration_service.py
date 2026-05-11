from datetime import datetime, timezone

from sqlalchemy import Select, select

from app.common.exceptions.base import AppException
from app.db.session.session import SessionLocal
from app.models.migration_task import MigrationTask
from app.schemas.orchestration.deployment import (
    MigrationCreateRequest,
    MigrationListResponse,
    MigrationTaskSummary,
)


class MigrationService:
    async def list_migrations(
        self,
        status: str | None = None,
        migration_type: str | None = None,
        limit: int = 50,
    ) -> MigrationListResponse:
        query: Select[tuple[MigrationTask]] = (
            select(MigrationTask).order_by(MigrationTask.created_at.desc()).limit(limit)
        )
        if status:
            query = query.where(MigrationTask.status == status)
        if migration_type:
            query = query.where(MigrationTask.migration_type == migration_type)

        async with SessionLocal() as session:
            result = await session.execute(query)
            tasks = result.scalars().all()
        return MigrationListResponse(items=[self._serialize(t) for t in tasks])

    async def get_migration(self, migration_id: str) -> MigrationTaskSummary:
        async with SessionLocal() as session:
            task = await session.get(MigrationTask, migration_id)
            if not task:
                raise AppException(
                    message="Migration task not found",
                    status_code=404,
                    error_code="migration_not_found",
                )
            return self._serialize(task)

    async def create_migration(
        self, payload: MigrationCreateRequest
    ) -> MigrationTaskSummary:
        async with SessionLocal() as session:
            task = MigrationTask(
                migration_type=payload.migration_type,
                source_ref=payload.source_ref,
                destination_ref=payload.destination_ref,
                resource_type=payload.resource_type,
                resource_id=payload.resource_id,
                status="queued",
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)

            return self._serialize(task)

    async def update_migration_progress(
        self, migration_id: str, progress: int, status: str | None = None
    ) -> MigrationTaskSummary:
        async with SessionLocal() as session:
            task = await session.get(MigrationTask, migration_id)
            if not task:
                raise AppException(
                    message="Migration task not found",
                    status_code=404,
                    error_code="migration_not_found",
                )
            task.progress = progress
            if status:
                task.status = status
            if status in {"succeeded", "failed"}:
                task.finished_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(task)
            return self._serialize(task)

    @staticmethod
    def _serialize(task: MigrationTask) -> MigrationTaskSummary:
        return MigrationTaskSummary(
            id=task.id,
            migration_type=task.migration_type,
            source_ref=task.source_ref,
            destination_ref=task.destination_ref,
            resource_type=task.resource_type,
            resource_id=task.resource_id,
            status=task.status,
            progress=task.progress,
            error_message=task.error_message,
            created_at=task.created_at.isoformat() if task.created_at else None,
            finished_at=task.finished_at.isoformat() if task.finished_at else None,
        )
