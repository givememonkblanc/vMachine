from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps.services import get_operation_task_service, get_operations_service
from app.schemas.core.operation_task import (
    OperationTaskListResponse,
    OperationTaskQueryParams,
    OperationTaskSummary,
)
from app.schemas.orchestration.operations_automation import (
    ScalingPolicyCreateRequest,
    ScalingPolicyListResponse,
    ScalingPolicySummary,
    ScheduledTaskCreateRequest,
    ScheduledTaskListResponse,
    ScheduledTaskSummary,
)
from app.services.core.operation_task_service import OperationTaskService
from app.services.orchestration.operations_service import OperationsService

router = APIRouter()


@router.get("/tasks", response_model=OperationTaskListResponse)
async def list_operation_tasks(
    params: Annotated[OperationTaskQueryParams, Depends()],
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> OperationTaskListResponse:
    """비동기로 실행된 리소스 생성/변경 작업(Operation Task)의 목록 및 처리 상태 조회"""
    items = await operation_task_service.list_tasks(
        limit=params.limit,
        state=params.state,
        target_type=params.target_type,
    )
    return OperationTaskListResponse(items=items)


@router.get("/tasks/{task_id}", response_model=OperationTaskSummary)
async def get_operation_task(
    task_id: str,
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> OperationTaskSummary:
    """특정 비동기 작업(Operation Task)의 상세 상태 및 결과(또는 에러 메시지) 조회"""
    return await operation_task_service.get_task(task_id)


@router.get("/scaling-policies", response_model=ScalingPolicyListResponse)
async def list_scaling_policies(
    operations_service: Annotated[OperationsService, Depends(get_operations_service)],
) -> ScalingPolicyListResponse:
    """오토스케일링 정책 목록을 조회합니다."""
    return await operations_service.list_scaling_policies()


@router.get("/scaling-policies/{policy_id}", response_model=ScalingPolicySummary)
async def get_scaling_policy(
    policy_id: str,
    operations_service: Annotated[OperationsService, Depends(get_operations_service)],
) -> ScalingPolicySummary:
    """특정 오토스케일링 정책의 상세 정보를 조회합니다."""
    return await operations_service.get_scaling_policy(policy_id)


@router.post(
    "/scaling-policies",
    response_model=ScalingPolicySummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_scaling_policy(
    payload: ScalingPolicyCreateRequest,
    operations_service: Annotated[OperationsService, Depends(get_operations_service)],
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> ScalingPolicySummary:
    """새로운 오토스케일링 정책을 생성합니다."""
    task = await operation_task_service.create_task(
        operation_type="create_scaling_policy",
        target_type="scaling_policy",
        target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")
    try:
        policy = await operations_service.create_scaling_policy(payload)
        _ = await operation_task_service.update_task(
            task.id, state="succeeded", target_id=policy.id
        )
        return policy.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(
            task.id, state="failed", error_message=str(exc)
        )
        raise


@router.delete("/scaling-policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scaling_policy(
    policy_id: str,
    operations_service: Annotated[OperationsService, Depends(get_operations_service)],
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> Response:
    """오토스케일링 정책을 삭제합니다."""
    task = await operation_task_service.create_task(
        operation_type="delete_scaling_policy",
        target_type="scaling_policy",
        target_id=policy_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")
    try:
        await operations_service.delete_scaling_policy(policy_id)
        _ = await operation_task_service.update_task(task.id, state="succeeded")
    except Exception as exc:
        _ = await operation_task_service.update_task(
            task.id, state="failed", error_message=str(exc)
        )
        raise
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response


@router.get("/scheduled-tasks", response_model=ScheduledTaskListResponse)
async def list_scheduled_tasks(
    operations_service: Annotated[OperationsService, Depends(get_operations_service)],
) -> ScheduledTaskListResponse:
    """예약된 주기적 작업 목록을 조회합니다."""
    return await operations_service.list_scheduled_tasks()


@router.get("/scheduled-tasks/{task_id}", response_model=ScheduledTaskSummary)
async def get_scheduled_task(
    task_id: str,
    operations_service: Annotated[OperationsService, Depends(get_operations_service)],
) -> ScheduledTaskSummary:
    """특정 예약 작업의 상세 정보를 조회합니다."""
    return await operations_service.get_scheduled_task(task_id)


@router.post(
    "/scheduled-tasks",
    response_model=ScheduledTaskSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_scheduled_task(
    payload: ScheduledTaskCreateRequest,
    operations_service: Annotated[OperationsService, Depends(get_operations_service)],
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> ScheduledTaskSummary:
    """새로운 예약 작업을 등록합니다. backup, health_check, cleanup 등의 유형 지원"""
    task = await operation_task_service.create_task(
        operation_type="create_scheduled_task",
        target_type="scheduled_task",
        target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")
    try:
        st = await operations_service.create_scheduled_task(payload)
        _ = await operation_task_service.update_task(
            task.id, state="succeeded", target_id=st.id
        )
        return st.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(
            task.id, state="failed", error_message=str(exc)
        )
        raise


@router.delete("/scheduled-tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scheduled_task(
    task_id: str,
    operations_service: Annotated[OperationsService, Depends(get_operations_service)],
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> Response:
    """예약 작업을 삭제합니다."""
    task = await operation_task_service.create_task(
        operation_type="delete_scheduled_task",
        target_type="scheduled_task",
        target_id=task_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")
    try:
        await operations_service.delete_scheduled_task(task_id)
        _ = await operation_task_service.update_task(task.id, state="succeeded")
    except Exception as exc:
        _ = await operation_task_service.update_task(
            task.id, state="failed", error_message=str(exc)
        )
        raise
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response
