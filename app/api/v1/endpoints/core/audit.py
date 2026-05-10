from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps.services import get_audit_service
from app.schemas.core.audit import AuditLogListResponse, AuditLogQueryParams
from app.services.core.audit_service import AuditService

router = APIRouter()


@router.get("/logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    params: Annotated[AuditLogQueryParams, Depends()],
    audit_service: Annotated[AuditService, Depends(get_audit_service)],
) -> AuditLogListResponse:
    """시스템 내에서 발생한 API 호출 및 리소스 상태 변경 감사(Audit) 로그 목록 조회"""
    items = await audit_service.list_audit_logs(
        limit=params.limit,
        resource_type=params.resource_type,
        status=params.status,
    )
    return AuditLogListResponse(items=items)
