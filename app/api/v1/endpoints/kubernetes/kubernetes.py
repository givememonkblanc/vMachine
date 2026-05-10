from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps.services import get_kubernetes_service, get_operation_task_service
from app.schemas.kubernetes import (
    DeploymentCreateRequest,
    DeploymentListResponse,
    DeploymentScaleRequest,
    DeploymentSummary,
    K8sClusterInfo,
    PodCreateRequest,
    PodListResponse,
    PodSummary,
    ServiceCreateRequest,
    ServiceListResponse,
    ServiceSummary,
)
from app.services.kubernetes.kubernetes_service import KubernetesService
from app.services.core.operation_task_service import OperationTaskService

router = APIRouter()


@router.get("/pods", response_model=PodListResponse)
def list_pods(
    kubernetes_service: Annotated[KubernetesService, Depends(get_kubernetes_service)],
) -> PodListResponse:
    """Kubernetes Pod 목록을 조회합니다."""
    return kubernetes_service.list_pods()


@router.get("/pods/{name}", response_model=PodSummary)
def get_pod(
    name: str,
    kubernetes_service: Annotated[KubernetesService, Depends(get_kubernetes_service)],
) -> PodSummary:
    """특정 Pod의 상세 정보를 조회합니다."""
    return kubernetes_service.get_pod(name)


@router.post("/pods", response_model=PodSummary, status_code=status.HTTP_201_CREATED)
async def create_pod(
    payload: PodCreateRequest,
    kubernetes_service: Annotated[KubernetesService, Depends(get_kubernetes_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> PodSummary:
    """새로운 Pod를 생성하며, 비동기 작업(Operation Task)으로 상태를 추적할 수 있음"""
    task = await operation_task_service.create_task(
        operation_type="create_pod",
        target_type="k8s_pod",
        target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        pod = kubernetes_service.create_pod(payload)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=pod.name)
        return pod.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", error_message=str(exc))
        raise


@router.delete("/pods/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pod(
    name: str,
    kubernetes_service: Annotated[KubernetesService, Depends(get_kubernetes_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> Response:
    """Pod를 영구 삭제합니다."""
    task = await operation_task_service.create_task(
        operation_type="delete_pod",
        target_type="k8s_pod",
        target_id=name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        kubernetes_service.delete_pod(name)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=name)
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=name, error_message=str(exc))
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response


@router.get("/deployments", response_model=DeploymentListResponse)
def list_deployments(
    kubernetes_service: Annotated[KubernetesService, Depends(get_kubernetes_service)],
) -> DeploymentListResponse:
    """Kubernetes Deployment 목록을 조회합니다."""
    return kubernetes_service.list_deployments()


@router.get("/deployments/{name}", response_model=DeploymentSummary)
def get_deployment(
    name: str,
    kubernetes_service: Annotated[KubernetesService, Depends(get_kubernetes_service)],
) -> DeploymentSummary:
    """특정 Deployment의 상세 정보를 조회합니다."""
    return kubernetes_service.get_deployment(name)


@router.post("/deployments", response_model=DeploymentSummary, status_code=status.HTTP_201_CREATED)
async def create_deployment(
    payload: DeploymentCreateRequest,
    kubernetes_service: Annotated[KubernetesService, Depends(get_kubernetes_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> DeploymentSummary:
    """새로운 Deployment를 생성하며, 비동기 작업(Operation Task)으로 상태를 추적할 수 있음"""
    task = await operation_task_service.create_task(
        operation_type="create_deployment",
        target_type="k8s_deployment",
        target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        dep = kubernetes_service.create_deployment(payload)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=dep.name)
        return dep.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", error_message=str(exc))
        raise


@router.delete("/deployments/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deployment(
    name: str,
    kubernetes_service: Annotated[KubernetesService, Depends(get_kubernetes_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> Response:
    """Deployment를 영구 삭제합니다."""
    task = await operation_task_service.create_task(
        operation_type="delete_deployment",
        target_type="k8s_deployment",
        target_id=name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        kubernetes_service.delete_deployment(name)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=name)
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=name, error_message=str(exc))
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response


@router.patch("/deployments/{name}/scale", response_model=DeploymentSummary)
async def scale_deployment(
    name: str,
    payload: DeploymentScaleRequest,
    kubernetes_service: Annotated[KubernetesService, Depends(get_kubernetes_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> DeploymentSummary:
    """Deployment의 복제본 수를 스케일 조정합니다."""
    task = await operation_task_service.create_task(
        operation_type="scale_deployment",
        target_type="k8s_deployment",
        target_id=name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        dep = kubernetes_service.scale_deployment(name, payload)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=dep.name)
        return dep.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=name, error_message=str(exc))
        raise


@router.get("/services", response_model=ServiceListResponse)
def list_services(
    kubernetes_service: Annotated[KubernetesService, Depends(get_kubernetes_service)],
) -> ServiceListResponse:
    """Kubernetes Service 목록을 조회합니다."""
    return kubernetes_service.list_services()


@router.get("/services/{name}", response_model=ServiceSummary)
def get_service(
    name: str,
    kubernetes_service: Annotated[KubernetesService, Depends(get_kubernetes_service)],
) -> ServiceSummary:
    """특정 Service의 상세 정보를 조회합니다."""
    return kubernetes_service.get_service(name)


@router.post("/services", response_model=ServiceSummary, status_code=status.HTTP_201_CREATED)
async def create_service(
    payload: ServiceCreateRequest,
    kubernetes_service: Annotated[KubernetesService, Depends(get_kubernetes_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> ServiceSummary:
    """새로운 Service를 생성하며, 비동기 작업(Operation Task)으로 상태를 추적할 수 있음"""
    task = await operation_task_service.create_task(
        operation_type="create_service",
        target_type="k8s_service",
        target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        svc = kubernetes_service.create_service(payload)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=svc.name)
        return svc.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", error_message=str(exc))
        raise


@router.delete("/services/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    name: str,
    kubernetes_service: Annotated[KubernetesService, Depends(get_kubernetes_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> Response:
    """Service를 영구 삭제합니다."""
    task = await operation_task_service.create_task(
        operation_type="delete_service",
        target_type="k8s_service",
        target_id=name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        kubernetes_service.delete_service(name)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=name)
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=name, error_message=str(exc))
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response


@router.get("/cluster", response_model=K8sClusterInfo)
def get_cluster_info(
    kubernetes_service: Annotated[KubernetesService, Depends(get_kubernetes_service)],
) -> K8sClusterInfo:
    """Kubernetes 클러스터의 노드 수, 네임스페이스, 버전 정보를 조회합니다."""
    return kubernetes_service.get_cluster_info()
