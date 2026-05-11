from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps.services import get_flavor_service, get_operation_task_service
from app.schemas.openstack.flavor import FlavorCreateRequest, FlavorListResponse, FlavorSummary
from app.services.openstack.flavor_service import FlavorService
from app.services.core.operation_task_service import OperationTaskService

router = APIRouter()


@router.get("", response_model=FlavorListResponse)
def list_flavors(
    flavor_service: Annotated[FlavorService, Depends(get_flavor_service)],
) -> FlavorListResponse:
    """가상 서버 생성에 사용할 수 있는 플레이버(컴퓨팅 스펙) 목록 조회"""
    return FlavorListResponse(items=flavor_service.list_flavors())


@router.get("/{flavor_id}", response_model=FlavorSummary)
def get_flavor(
    flavor_id: str,
    flavor_service: Annotated[FlavorService, Depends(get_flavor_service)],
) -> FlavorSummary:
    """특정 플레이버의 상세 정보 조회"""
    return flavor_service.get_flavor(flavor_id)


@router.post("", response_model=FlavorSummary, status_code=status.HTTP_201_CREATED)
async def create_flavor(
    payload: FlavorCreateRequest,
    flavor_service: Annotated[FlavorService, Depends(get_flavor_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> FlavorSummary:
    """새로운 플레이버(컴퓨팅 스펙) 생성"""
    task = await operation_task_service.create_task(
        operation_type="create_flavor",
        target_type="flavor",
        target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        flavor = flavor_service.create_flavor(payload)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=flavor.id)
        return flavor.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", error_message=str(exc))
        raise


@router.delete("/{flavor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flavor(
    flavor_id: str,
    flavor_service: Annotated[FlavorService, Depends(get_flavor_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> Response:
    """플레이버 영구 삭제"""
    task = await operation_task_service.create_task(
        operation_type="delete_flavor",
        target_type="flavor",
        target_id=flavor_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        flavor_service.delete_flavor(flavor_id)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=flavor_id)
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=flavor_id, error_message=str(exc))
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response
