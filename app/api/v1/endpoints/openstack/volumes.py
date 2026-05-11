from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps.services import get_operation_task_service, get_volume_service
from app.schemas.openstack.volume import (
    VolumeCreateRequest,
    VolumeListResponse,
    VolumeSummary,
)
from app.services.core.operation_task_service import OperationTaskService
from app.services.openstack.volume_service import VolumeService

router = APIRouter()


@router.get("", response_model=VolumeListResponse)
def list_volumes(
    volume_service: Annotated[VolumeService, Depends(get_volume_service)],
) -> VolumeListResponse:
    """블록 스토리지(볼륨) 목록 조회"""
    return VolumeListResponse(items=volume_service.list_volumes())


@router.get("/{volume_id}", response_model=VolumeSummary)
def get_volume(
    volume_id: str,
    volume_service: Annotated[VolumeService, Depends(get_volume_service)],
) -> VolumeSummary:
    """특정 블록 스토리지(볼륨)의 상세 정보 조회"""
    return volume_service.get_volume(volume_id)


@router.post("", response_model=VolumeSummary, status_code=status.HTTP_201_CREATED)
async def create_volume(
    payload: VolumeCreateRequest,
    volume_service: Annotated[VolumeService, Depends(get_volume_service)],
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> VolumeSummary:
    """새로운 블록 스토리지(데이터 볼륨 또는 부팅 볼륨) 생성"""
    task = await operation_task_service.create_task(
        operation_type="create_volume",
        target_type="volume",
        target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        response = volume_service.create_volume(payload)
        _ = await operation_task_service.update_task(
            task.id, state="succeeded", target_id=response.id
        )
        return response.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(
            task.id, state="failed", error_message=str(exc)
        )
        raise


@router.delete("/{volume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_volume(
    volume_id: str,
    volume_service: Annotated[VolumeService, Depends(get_volume_service)],
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> Response:
    """블록 스토리지(볼륨) 영구 삭제"""
    task = await operation_task_service.create_task(
        operation_type="delete_volume",
        target_type="volume",
        target_id=volume_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        volume_service.delete_volume(volume_id)
        _ = await operation_task_service.update_task(
            task.id, state="succeeded", target_id=volume_id
        )
    except Exception as exc:
        _ = await operation_task_service.update_task(
            task.id, state="failed", target_id=volume_id, error_message=str(exc)
        )
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response
