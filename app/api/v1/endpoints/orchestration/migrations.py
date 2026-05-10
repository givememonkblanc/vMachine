from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps.services import get_migration_service, get_operation_task_service
from app.schemas.deployment import (
    MigrationCreateRequest,
    MigrationListResponse,
    MigrationTaskSummary,
)
from app.services.orchestration.migration_service import MigrationService
from app.services.core.operation_task_service import OperationTaskService

router = APIRouter()


@router.get("", response_model=MigrationListResponse)
async def list_migrations(
    migration_service: Annotated[MigrationService, Depends(get_migration_service)],
    status_filter: str | None = None,
    migration_type: str | None = None,
    limit: int = 50,
) -> MigrationListResponse:
    """마이그레이션 작업 목록을 조회합니다. 상태와 유형으로 필터링 가능"""
    return await migration_service.list_migrations(
        status=status_filter, migration_type=migration_type, limit=limit
    )


@router.get("/{migration_id}", response_model=MigrationTaskSummary)
async def get_migration(
    migration_id: str,
    migration_service: Annotated[MigrationService, Depends(get_migration_service)],
) -> MigrationTaskSummary:
    """특정 마이그레이션 작업의 상세 정보를 조회합니다."""
    return await migration_service.get_migration(migration_id)


@router.post("", response_model=MigrationTaskSummary, status_code=status.HTTP_201_CREATED)
async def create_migration(
    payload: MigrationCreateRequest,
    migration_service: Annotated[MigrationService, Depends(get_migration_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> MigrationTaskSummary:
    """새로운 마이그레이션 작업을 생성합니다. cold/live/vmware 유형 지원"""
    task = await operation_task_service.create_task(
        operation_type=f"{payload.migration_type}_migration",
        target_type="migration",
        target_id=payload.source_ref,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        migration = await migration_service.create_migration(payload)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=migration.id)
        return migration.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", error_message=str(exc))
        raise


@router.post("/{migration_id}/progress", response_model=MigrationTaskSummary)
async def update_migration_progress(
    migration_id: str,
    progress: int,
    migration_service: Annotated[MigrationService, Depends(get_migration_service)],
) -> MigrationTaskSummary:
    """마이그레이션 작업의 진행률을 업데이트합니다."""
    return await migration_service.update_migration_progress(migration_id, progress)
