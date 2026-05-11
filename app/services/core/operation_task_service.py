from datetime import datetime, timezone

from sqlalchemy import Select, select

from app.common.exceptions.base import AppException
from app.db.session.session import SessionLocal
from app.models.operation_task import OperationTask
from app.schemas.core.operation_task import OperationTaskSummary


class OperationTaskService:
    async def create_task(
        self,
        operation_type: str,
        target_type: str,
        target_id: str | None = None,
    ) -> OperationTaskSummary:
        db_task = OperationTask(
            operation_type=operation_type,
            target_type=target_type,
            target_id=target_id,
            state="queued",
        )

        async with SessionLocal() as session:
            session.add(db_task)
            await session.commit()
            await session.refresh(db_task)

        return self._serialize_task(db_task)

    async def update_task(
        self,
        task_id: str,
        state: str,
        target_id: str | None = None,
        error_message: str | None = None,
    ) -> OperationTaskSummary:
        async with SessionLocal() as session:
            task = await session.get(OperationTask, task_id)
            if not task:
                raise AppException(message="Operation task not found", status_code=404, error_code="task_not_found")

            task.state = state
            if target_id is not None:
                task.target_id = target_id
            task.error_message = error_message
            if state in {"succeeded", "failed"}:
                task.finished_at = datetime.now(timezone.utc)

            await session.commit()
            await session.refresh(task)

        return self._serialize_task(task)

    async def get_task(self, task_id: str) -> OperationTaskSummary:
        async with SessionLocal() as session:
            task = await session.get(OperationTask, task_id)
            if not task:
                raise AppException(message="Operation task not found", status_code=404, error_code="task_not_found")

        return self._serialize_task(task)

    async def list_tasks(
        self,
        limit: int = 50,
        state: str | None = None,
        target_type: str | None = None,
    ) -> list[OperationTaskSummary]:
        query: Select[tuple[OperationTask]] = select(OperationTask).order_by(OperationTask.submitted_at.desc()).limit(limit)

        if state:
            query = query.where(OperationTask.state == state)
        if target_type:
            query = query.where(OperationTask.target_type == target_type)

        async with SessionLocal() as session:
            result = await session.execute(query)
            tasks = result.scalars().all()

        return [self._serialize_task(task) for task in tasks]

    def _serialize_task(self, task: OperationTask) -> OperationTaskSummary:
        return OperationTaskSummary(
            id=task.id,
            operation_type=task.operation_type,
            target_type=task.target_type,
            target_id=task.target_id,
            state=task.state,
            error_message=task.error_message,
            submitted_at=task.submitted_at.isoformat() if task.submitted_at else None,
            finished_at=task.finished_at.isoformat() if task.finished_at else None,
        )
