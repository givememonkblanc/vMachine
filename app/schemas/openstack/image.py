from pydantic import BaseModel, Field


class ImageCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="이미지 이름")
    container_format: str = Field(default="bare", description="컨테이너 포맷 (bare, ovf, aki 등)")
    disk_format: str = Field(default="qcow2", description="디스크 포맷 (qcow2, raw, iso 등)")
    min_disk: int = Field(default=0, ge=0, description="이미지 부팅에 필요한 최소 디스크 크기 (GB)")
    min_ram: int = Field(default=0, ge=0, description="이미지 부팅에 필요한 최소 RAM 크기 (MB)")
    visibility: str = Field(default="private", description="공개 범위 (public, private)")
    protected: bool = Field(default=False, description="삭제 보호 여부")


class ImageSummary(BaseModel):
    id: str | None = None
    name: str | None = None
    status: str | None = None
    visibility: str | None = None
    container_format: str | None = None
    disk_format: str | None = None
    operation_task_id: str | None = None


class ImageListResponse(BaseModel):
    items: list[ImageSummary]
