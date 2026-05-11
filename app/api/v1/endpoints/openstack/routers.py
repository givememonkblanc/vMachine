from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps.services import get_operation_task_service, get_router_service
from app.schemas.openstack.router import (
    RouterCreateRequest,
    RouterCreateResponse,
    RouterInterfaceRequest,
    RouterListResponse,
    RouterSummary,
)
from app.services.core.operation_task_service import OperationTaskService
from app.services.openstack.router_service import RouterService

router = APIRouter()


@router.get("", response_model=RouterListResponse)
def list_routers(
    router_service: Annotated[RouterService, Depends(get_router_service)],
) -> RouterListResponse:
    """가상 라우터 목록 조회"""
    return RouterListResponse(items=router_service.list_routers())


@router.get("/{router_id}", response_model=RouterSummary)
def get_router(
    router_id: str,
    router_service: Annotated[RouterService, Depends(get_router_service)],
) -> RouterSummary:
    """특정 가상 라우터의 상세 정보 조회"""
    return router_service.get_router(router_id)


@router.post(
    "", response_model=RouterCreateResponse, status_code=status.HTTP_201_CREATED
)
async def create_router(
    payload: RouterCreateRequest,
    router_service: Annotated[RouterService, Depends(get_router_service)],
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> RouterCreateResponse:
    """외부망(Gateway) 연결이 가능한 새로운 라우터 생성"""
    task = await operation_task_service.create_task(
        operation_type="create_router",
        target_type="router",
        target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        response = router_service.create_router(payload)
        _ = await operation_task_service.update_task(
            task.id, state="succeeded", target_id=response.router_id
        )
        return response.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(
            task.id, state="failed", error_message=str(exc)
        )
        raise


@router.delete("/{router_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_router(
    router_id: str,
    router_service: Annotated[RouterService, Depends(get_router_service)],
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> Response:
    """가상 라우터 영구 삭제"""
    task = await operation_task_service.create_task(
        operation_type="delete_router",
        target_type="router",
        target_id=router_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        router_service.delete_router(router_id)
        _ = await operation_task_service.update_task(
            task.id, state="succeeded", target_id=router_id
        )
    except Exception as exc:
        _ = await operation_task_service.update_task(
            task.id, state="failed", target_id=router_id, error_message=str(exc)
        )
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response


@router.post("/{router_id}/interfaces", status_code=status.HTTP_204_NO_CONTENT)
async def add_interface(
    router_id: str,
    payload: RouterInterfaceRequest,
    router_service: Annotated[RouterService, Depends(get_router_service)],
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> Response:
    """라우터에 특정 서브넷을 인터페이스로 추가하여 네트워크 간 라우팅 활성화"""
    task = await operation_task_service.create_task(
        operation_type="add_interface",
        target_type="router",
        target_id=router_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        router_service.add_interface(router_id, payload.subnet_id)
        _ = await operation_task_service.update_task(
            task.id, state="succeeded", target_id=router_id
        )
    except Exception as exc:
        _ = await operation_task_service.update_task(
            task.id, state="failed", target_id=router_id, error_message=str(exc)
        )
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response


@router.delete(
    "/{router_id}/interfaces/{subnet_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_interface(
    router_id: str,
    subnet_id: str,
    router_service: Annotated[RouterService, Depends(get_router_service)],
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> Response:
    """라우터에서 특정 서브넷 인터페이스 연결 해제"""
    task = await operation_task_service.create_task(
        operation_type="remove_interface",
        target_type="router",
        target_id=router_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        router_service.remove_interface(router_id, subnet_id)
        _ = await operation_task_service.update_task(
            task.id, state="succeeded", target_id=router_id
        )
    except Exception as exc:
        _ = await operation_task_service.update_task(
            task.id, state="failed", target_id=router_id, error_message=str(exc)
        )
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response
