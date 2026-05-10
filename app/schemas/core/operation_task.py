from pydantic import BaseModel, Field


class OperationTaskQueryParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=200, description="최대 반환 개수")
    state: str | None = Field(default=None, description="상태 필터링 (예: queued, running, succeeded, failed)")
    target_type: str | None = Field(default=None, description="타겟 리소스 타입 (예: server, network, volume)")


class OperationTaskSummary(BaseModel):
    id: str
    operation_type: str
    target_type: str
    target_id: str | None = None
    state: str
    error_message: str | None = None
    submitted_at: str | None = None
    finished_at: str | None = None


class OperationTaskListResponse(BaseModel):
    items: list[OperationTaskSummary]
