from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="프로젝트 이름")
    description: str | None = Field(default=None, description="프로젝트 설명")
    enabled: bool = Field(default=True, description="프로젝트 활성화 여부")


class ProjectSummary(BaseModel):
    id: str | None = None
    name: str | None = None
    domain_id: str | None = None
    enabled: bool | None = None
    operation_task_id: str | None = None


class ProjectListResponse(BaseModel):
    items: list[ProjectSummary]
