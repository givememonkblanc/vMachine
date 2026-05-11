from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps.services import get_cluster_service, get_operation_task_service
from app.schemas.orchestration.deployment import (
    BatchDeployRequest,
    BatchDeployResponse,
    ClusterCreateRequest,
    ClusterListResponse,
    ClusterSummary,
)
from app.services.orchestration.cluster_service import ClusterService
from app.services.core.operation_task_service import OperationTaskService

router = APIRouter()


@router.get("", response_model=ClusterListResponse)
async def list_clusters(
    cluster_service: Annotated[ClusterService, Depends(get_cluster_service)],
) -> ClusterListResponse:
    """클러스터 목록을 조회합니다."""
    return await cluster_service.list_clusters()


@router.get("/{cluster_id}", response_model=ClusterSummary)
async def get_cluster(
    cluster_id: str,
    cluster_service: Annotated[ClusterService, Depends(get_cluster_service)],
) -> ClusterSummary:
    """특정 클러스터의 상세 정보를 조회합니다."""
    return await cluster_service.get_cluster(cluster_id)


@router.post("", response_model=ClusterSummary, status_code=status.HTTP_201_CREATED)
async def create_cluster(
    payload: ClusterCreateRequest,
    cluster_service: Annotated[ClusterService, Depends(get_cluster_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> ClusterSummary:
    """새로운 클러스터를 생성합니다."""
    task = await operation_task_service.create_task(
        operation_type="create_cluster",
        target_type="cluster",
        target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        cluster = await cluster_service.create_cluster(payload)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=cluster.id)
        return cluster.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", error_message=str(exc))
        raise


@router.delete("/{cluster_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cluster(
    cluster_id: str,
    cluster_service: Annotated[ClusterService, Depends(get_cluster_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> Response:
    """클러스터를 삭제합니다."""
    task = await operation_task_service.create_task(
        operation_type="delete_cluster",
        target_type="cluster",
        target_id=cluster_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        await cluster_service.delete_cluster(cluster_id)
        _ = await operation_task_service.update_task(task.id, state="succeeded")
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", error_message=str(exc))
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response


@router.post("/{cluster_id}/deploy", response_model=BatchDeployResponse)
async def batch_deploy(
    cluster_id: str,
    payload: BatchDeployRequest,
    cluster_service: Annotated[ClusterService, Depends(get_cluster_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> BatchDeployResponse:
    """클러스터에 다수 인스턴스를 일괄 배포합니다."""
    task = await operation_task_service.create_task(
        operation_type="batch_deploy",
        target_type="cluster",
        target_id=cluster_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        result = await cluster_service.batch_deploy(cluster_id, payload)
        _ = await operation_task_service.update_task(task.id, state="succeeded")
        return result.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", error_message=str(exc))
        raise
