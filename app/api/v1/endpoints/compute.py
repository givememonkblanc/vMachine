from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps.services import get_compute_service, get_operation_task_service
from app.schemas.compute import (
    ServerActionRequest,
    ServerActionResponse,
    ServerCreateRequest,
    ServerDetail,
    ServerImageCreateRequest,
    ServerImageCreateResponse,
    ServerListResponse,
    ServerResizeActionRequest,
    ServerResizeRequest,
    ServerSummary,
    VolumeAttachRequest,
)
from app.services.compute_service import ComputeService
from app.services.operation_task_service import OperationTaskService

router = APIRouter()


@router.get("/servers", response_model=ServerListResponse)
def list_servers(
    compute_service: Annotated[ComputeService, Depends(get_compute_service)],
) -> ServerListResponse:
    """생성된 가상 서버(VM 인스턴스) 목록 조회"""
    return ServerListResponse(items=compute_service.list_servers())


@router.post("/servers", response_model=ServerSummary, status_code=status.HTTP_201_CREATED)
async def create_server(
    payload: ServerCreateRequest,
    compute_service: Annotated[ComputeService, Depends(get_compute_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> ServerSummary:
    """새로운 가상 서버(VM)를 생성하며, 비동기 작업(Operation Task)으로 상태를 추적할 수 있음"""
    task = await operation_task_service.create_task(
        operation_type="create_server",
        target_type="server",
        target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        server = compute_service.create_server(payload)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=server.id)
        return server.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", error_message=str(exc))
        raise


@router.get("/servers/{server_id}", response_model=ServerDetail)
def get_server(
    server_id: str,
    compute_service: Annotated[ComputeService, Depends(get_compute_service)],
) -> ServerDetail:
    """특정 가상 서버(VM)의 IP 주소, 메타데이터 등을 포함한 상세 정보 조회"""
    return compute_service.get_server(server_id)


@router.post("/servers/{server_id}/actions", response_model=ServerActionResponse)
async def server_action(
    server_id: str,
    payload: ServerActionRequest,
    compute_service: Annotated[ComputeService, Depends(get_compute_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> ServerActionResponse:
    """가상 서버에 대한 전원 제어(시작, 정지, 재부팅) 액션 수행"""
    task = await operation_task_service.create_task(
        operation_type=f"{payload.action}_server",
        target_type="server",
        target_id=server_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        response = compute_service.perform_action(server_id, payload.action)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=server_id)
        return response.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=server_id, error_message=str(exc))
        raise


@router.delete("/servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_server(
    server_id: str,
    compute_service: Annotated[ComputeService, Depends(get_compute_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> Response:
    """가상 서버 영구 삭제"""
    task = await operation_task_service.create_task(
        operation_type="delete_server",
        target_type="server",
        target_id=server_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        compute_service.delete_server(server_id)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=server_id)
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=server_id, error_message=str(exc))
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response


@router.post("/servers/{server_id}/volumes", status_code=status.HTTP_204_NO_CONTENT)
async def attach_volume(
    server_id: str,
    payload: VolumeAttachRequest,
    compute_service: Annotated[ComputeService, Depends(get_compute_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> Response:
    """특정 가상 서버에 블록 스토리지(볼륨) 연결"""
    task = await operation_task_service.create_task(
        operation_type="attach_volume",
        target_type="server",
        target_id=server_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        compute_service.attach_volume(server_id, payload.volume_id)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=server_id)
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=server_id, error_message=str(exc))
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response


@router.delete("/servers/{server_id}/volumes/{volume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_volume(
    server_id: str,
    volume_id: str,
    compute_service: Annotated[ComputeService, Depends(get_compute_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> Response:
    """특정 가상 서버에서 연결된 블록 스토리지(볼륨) 해제"""
    task = await operation_task_service.create_task(
        operation_type="detach_volume",
        target_type="server",
        target_id=server_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        compute_service.detach_volume(server_id, volume_id)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=server_id)
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=server_id, error_message=str(exc))
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response


@router.post("/servers/{server_id}/resize", status_code=status.HTTP_202_ACCEPTED)
async def resize_server(
    server_id: str,
    payload: ServerResizeRequest,
    compute_service: Annotated[ComputeService, Depends(get_compute_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> Response:
    """가상 서버의 Flavor(사양)를 변경합니다. 변경 후에는 confirm 또는 revert 액션으로 적용을 완료하거나 취소할 수 있음"""
    task = await operation_task_service.create_task(
        operation_type="resize_server",
        target_type="server",
        target_id=server_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        compute_service.resize_server(server_id, payload.flavor_id)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=server_id)
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=server_id, error_message=str(exc))
        raise

    response = Response(status_code=status.HTTP_202_ACCEPTED)
    response.headers["X-Operation-Task-ID"] = task.id
    return response


@router.post("/servers/{server_id}/resize/action")
async def resize_server_action(
    server_id: str,
    payload: ServerResizeActionRequest,
    compute_service: Annotated[ComputeService, Depends(get_compute_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> dict[str, str]:
    """Resize(사양 변경) 이후 confirm(적용) 또는 revert(취소) 액션을 수행"""
    action_label = "confirm_resize" if payload.action == "confirm" else "revert_resize"
    task = await operation_task_service.create_task(
        operation_type=action_label,
        target_type="server",
        target_id=server_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        if payload.action == "confirm":
            compute_service.confirm_resize(server_id)
        else:
            compute_service.revert_resize(server_id)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=server_id)
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=server_id, error_message=str(exc))
        raise

    return {"status": payload.action, "operation_task_id": task.id}


@router.post("/servers/{server_id}/snapshots", response_model=ServerImageCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_server_snapshot(
    server_id: str,
    payload: ServerImageCreateRequest,
    compute_service: Annotated[ComputeService, Depends(get_compute_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> ServerImageCreateResponse:
    """가상 서버의 현재 상태를 스냅샷 이미지로 생성"""
    task = await operation_task_service.create_task(
        operation_type="create_server_image",
        target_type="server",
        target_id=server_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        image_id = compute_service.create_server_image(server_id, payload.name)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=server_id)
        return ServerImageCreateResponse(
            server_id=server_id,
            image_name=payload.name,
            image_id=image_id,
            operation_task_id=task.id,
        )
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=server_id, error_message=str(exc))
        raise
