from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps.services import get_network_service, get_operation_task_service
from app.schemas.openstack.network import NetworkCreateRequest, NetworkCreateResponse, NetworkDetail, NetworkListResponse
from app.services.openstack.network_service import NetworkService
from app.services.core.operation_task_service import OperationTaskService

router = APIRouter()


@router.get("", response_model=NetworkListResponse)
def list_networks(
    network_service: Annotated[NetworkService, Depends(get_network_service)],
) -> NetworkListResponse:
    """가상 네트워크(VPC) 목록 조회"""
    return NetworkListResponse(items=network_service.list_networks())


@router.get("/{network_id}", response_model=NetworkDetail)
def get_network(
    network_id: str,
    network_service: Annotated[NetworkService, Depends(get_network_service)],
) -> NetworkDetail:
    """특정 네트워크 및 연결된 서브넷 상세 정보 조회"""
    return network_service.get_network(network_id)


@router.post("", response_model=NetworkCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_network(
    payload: NetworkCreateRequest,
    network_service: Annotated[NetworkService, Depends(get_network_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> NetworkCreateResponse:
    """새로운 네트워크와 해당 네트워크 내 서브넷을 일괄 생성"""
    task = await operation_task_service.create_task(
        operation_type="create_network",
        target_type="network",
        target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        response = network_service.create_network(payload)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=response.network_id)
        return response.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", error_message=str(exc))
        raise


@router.delete("/{network_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_network(
    network_id: str,
    network_service: Annotated[NetworkService, Depends(get_network_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> Response:
    """가상 네트워크 및 소속 서브넷 영구 삭제"""
    task = await operation_task_service.create_task(
        operation_type="delete_network",
        target_type="network",
        target_id=network_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        network_service.delete_network(network_id)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=network_id)
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=network_id, error_message=str(exc))
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response
