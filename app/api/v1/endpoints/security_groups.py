from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps.services import get_operation_task_service, get_security_group_service
from app.schemas.security_group import (
    SecurityGroupCreateRequest,
    SecurityGroupCreateResponse,
    SecurityGroupDetail,
    SecurityGroupListResponse,
    SecurityGroupRuleCreateRequest,
    SecurityGroupRuleCreateResponse,
)
from app.services.operation_task_service import OperationTaskService
from app.services.security_group_service import SecurityGroupService

router = APIRouter()


@router.get("", response_model=SecurityGroupListResponse)
def list_security_groups(
    security_group_service: Annotated[SecurityGroupService, Depends(get_security_group_service)],
) -> SecurityGroupListResponse:
    """가상 네트워크 보안그룹 목록 조회"""
    return SecurityGroupListResponse(items=security_group_service.list_security_groups())


@router.get("/{security_group_id}", response_model=SecurityGroupDetail)
def get_security_group(
    security_group_id: str,
    security_group_service: Annotated[SecurityGroupService, Depends(get_security_group_service)],
) -> SecurityGroupDetail:
    """보안그룹의 상세 정보 및 등록된 룰(Rule) 목록 조회"""
    return security_group_service.get_security_group(security_group_id)


@router.post("", response_model=SecurityGroupCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_security_group(
    payload: SecurityGroupCreateRequest,
    security_group_service: Annotated[SecurityGroupService, Depends(get_security_group_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> SecurityGroupCreateResponse:
    """새로운 네트워크 보안그룹 생성"""
    task = await operation_task_service.create_task(
        operation_type="create_security_group",
        target_type="security_group",
        target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        response = security_group_service.create_security_group(payload)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=response.security_group_id)
        return response.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", error_message=str(exc))
        raise


@router.delete("/{security_group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_security_group(
    security_group_id: str,
    security_group_service: Annotated[SecurityGroupService, Depends(get_security_group_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> Response:
    """네트워크 보안그룹 영구 삭제"""
    task = await operation_task_service.create_task(
        operation_type="delete_security_group",
        target_type="security_group",
        target_id=security_group_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        security_group_service.delete_security_group(security_group_id)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=security_group_id)
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=security_group_id, error_message=str(exc))
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response


@router.post("/{security_group_id}/rules", response_model=SecurityGroupRuleCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_security_group_rule(
    security_group_id: str,
    payload: SecurityGroupRuleCreateRequest,
    security_group_service: Annotated[SecurityGroupService, Depends(get_security_group_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> SecurityGroupRuleCreateResponse:
    """특정 보안그룹에 새로운 인바운드/아웃바운드 허용 룰(Rule) 추가"""
    task = await operation_task_service.create_task(
        operation_type="create_security_group_rule",
        target_type="security_group",
        target_id=security_group_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        response = security_group_service.create_rule(security_group_id, payload)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=response.rule_id)
        return response.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=security_group_id, error_message=str(exc))
        raise


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_security_group_rule(
    rule_id: str,
    security_group_service: Annotated[SecurityGroupService, Depends(get_security_group_service)],
    operation_task_service: Annotated[OperationTaskService, Depends(get_operation_task_service)],
) -> Response:
    """보안그룹에 등록된 특정 룰(Rule) 삭제"""
    task = await operation_task_service.create_task(
        operation_type="delete_security_group_rule",
        target_type="security_group_rule",
        target_id=rule_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        security_group_service.delete_rule(rule_id)
        _ = await operation_task_service.update_task(task.id, state="succeeded", target_id=rule_id)
    except Exception as exc:
        _ = await operation_task_service.update_task(task.id, state="failed", target_id=rule_id, error_message=str(exc))
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response
