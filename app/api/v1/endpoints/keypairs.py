from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps.services import get_keypair_service, get_operation_task_service
from app.schemas.keypair import KeypairCreateRequest, KeypairCreateResponse, KeypairListResponse, KeypairSummary
from app.services.openstack.keypair_service import KeypairService
from app.services.core.operation_task_service import OperationTaskService

router = APIRouter()


@router.get("", response_model=KeypairListResponse)
def list_keypairs(
    keypair_service: Annotated[KeypairService, Depends(get_keypair_service)],
) -> KeypairListResponse:
    """가상 서버 접근용 SSH 키페어 목록 조회"""
    return KeypairListResponse(items=keypair_service.list_keypairs())


@router.get("/{keypair_name}", response_model=KeypairSummary)
def get_keypair(
    keypair_name: str,
    keypair_service: Annotated[KeypairService, Depends(get_keypair_service)],
) -> KeypairSummary:
    """특정 SSH 키페어의 상세 정보 조회"""
    return keypair_service.get_keypair(keypair_name)


@router.post("", response_model=KeypairCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_keypair(
    payload: KeypairCreateRequest,
    keypair_service: Annotated[KeypairService, Depends(get_keypair_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> KeypairCreateResponse:
    """새로운 SSH 키페어 발급 또는 기존 공개키 등록"""
    task = await operation_task_service.create_task(
        operation_type="create_keypair",
        target_type="keypair",
        target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        response = keypair_service.create_keypair(payload)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=payload.name)
        return response.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", error_message=str(exc))
        raise


@router.delete("/{keypair_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_keypair(
    keypair_name: str,
    keypair_service: Annotated[KeypairService, Depends(get_keypair_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> Response:
    """SSH 키페어 영구 삭제"""
    task = await operation_task_service.create_task(
        operation_type="delete_keypair",
        target_type="keypair",
        target_id=keypair_name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        keypair_service.delete_keypair(keypair_name)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=keypair_name)
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=keypair_name, error_message=str(exc))
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response
