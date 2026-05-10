from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps.services import get_operation_task_service, get_tenant_service
from app.schemas.identity.tenant import ProjectCreateRequest, ProjectListResponse, ProjectSummary
from app.services.core.operation_task_service import OperationTaskService
from app.services.identity.tenant_service import TenantService

router = APIRouter()


@router.get("/projects", response_model=ProjectListResponse)
def list_projects(
    tenant_service: Annotated[TenantService, Depends(get_tenant_service)],
) -> ProjectListResponse:
    """현재 인증된 계정의 권한 내에 있는 프로젝트(테넌트) 목록 조회"""
    return ProjectListResponse(items=tenant_service.list_projects())


@router.get("/projects/{project_id}", response_model=ProjectSummary)
def get_project(
    project_id: str,
    tenant_service: Annotated[TenantService, Depends(get_tenant_service)],
) -> ProjectSummary:
    """특정 프로젝트의 상세 정보 조회"""
    return tenant_service.get_project(project_id)


@router.post("/projects", response_model=ProjectSummary, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreateRequest,
    tenant_service: Annotated[TenantService, Depends(get_tenant_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> ProjectSummary:
    """새로운 프로젝트(테넌트) 생성"""
    task = await operation_task_service.create_task(
        operation_type="create_project",
        target_type="project",
        target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        project = tenant_service.create_project(payload)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=project.id)
        return project.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", error_message=str(exc))
        raise


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: str,
    tenant_service: Annotated[TenantService, Depends(get_tenant_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> Response:
    """프로젝트(테넌트) 영구 삭제"""
    task = await operation_task_service.create_task(
        operation_type="delete_project",
        target_type="project",
        target_id=project_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        tenant_service.delete_project(project_id)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=project_id)
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=project_id, error_message=str(exc))
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response
