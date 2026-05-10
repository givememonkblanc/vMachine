from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps.services import get_operation_task_service, get_storage_service
from app.schemas.operations_automation import (
    StoragePoolCreateRequest,
    StoragePoolListResponse,
    StoragePoolSummary,
)
from app.services.operation_task_service import OperationTaskService
from app.services.storage_service import StorageService

router = APIRouter()


@router.get("/pools", response_model=StoragePoolListResponse)
async def list_pools(
    storage_service: Annotated[StorageService, Depends(get_storage_service)],
) -> StoragePoolListResponse:
    """SDS 스토리지 풀 목록을 조회합니다."""
    return await storage_service.list_pools()


@router.get("/pools/{pool_id}", response_model=StoragePoolSummary)
async def get_pool(
    pool_id: str,
    storage_service: Annotated[StorageService, Depends(get_storage_service)],
) -> StoragePoolSummary:
    """특정 스토리지 풀의 상세 정보를 조회합니다."""
    return await storage_service.get_pool(pool_id)


@router.post("/pools", response_model=StoragePoolSummary, status_code=status.HTTP_201_CREATED)
async def create_pool(
    payload: StoragePoolCreateRequest,
    storage_service: Annotated[StorageService, Depends(get_storage_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> StoragePoolSummary:
    """새로운 SDS 스토리지 풀을 생성합니다. ceph, nfs, lvm 유형 지원"""
    task = await operation_task_service.create_task(
        operation_type="create_storage_pool", target_type="storage_pool", target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")
    try:
        pool = await storage_service.create_pool(payload)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=pool.id)
        return pool.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", error_message=str(exc))
        raise


@router.delete("/pools/{pool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pool(
    pool_id: str,
    storage_service: Annotated[StorageService, Depends(get_storage_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> Response:
    """스토리지 풀을 삭제합니다."""
    task = await operation_task_service.create_task(
        operation_type="delete_storage_pool", target_type="storage_pool", target_id=pool_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")
    try:
        await storage_service.delete_pool(pool_id)
        _ = await operation_task_service.update_task(task.id, state="succeeded")
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", error_message=str(exc))
        raise
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response
