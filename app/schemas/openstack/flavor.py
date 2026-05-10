from pydantic import BaseModel, Field


class FlavorCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="플레이버 이름")
    vcpus: int = Field(..., gt=0, description="vCPU 개수")
    ram: int = Field(..., gt=0, description="RAM 크기 (MB)")
    disk: int = Field(..., ge=0, description="디스크 크기 (GB)")


class FlavorSummary(BaseModel):
    id: str | None = None
    name: str | None = None
    vcpus: int | None = None
    ram: int | None = None
    disk: int | None = None
    operation_task_id: str | None = None


class FlavorListResponse(BaseModel):
    items: list[FlavorSummary]
