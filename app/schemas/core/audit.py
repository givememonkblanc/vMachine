from pydantic import BaseModel, Field


class AuditLogQueryParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=200, description="최대 반환 개수")
    resource_type: str | None = Field(default=None, description="리소스 타입 필터링 (예: server, network)")
    status: str | None = Field(default=None, description="성공 여부 필터링 (예: success, failure)")


class AuditLogSummary(BaseModel):
    id: str
    actor: str | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    status: str
    request_id: str | None = None
    payload: dict[str, object] | None = None
    created_at: str | None = None


class AuditLogListResponse(BaseModel):
    items: list[AuditLogSummary]
