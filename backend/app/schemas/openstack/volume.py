from pydantic import BaseModel, Field


class VolumeSummary(BaseModel):
    id: str | None = None
    name: str | None = None
    status: str | None = None
    size: int | None = None
    bootable: str | None = None
    operation_task_id: str | None = None


class VolumeCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="생성할 볼륨 이름")
    size: int = Field(..., gt=0, description="생성할 볼륨의 크기 (GiB 단위)")
    description: str | None = Field(default=None, description="볼륨에 대한 설명")
    image_id: str | None = Field(default=None, description="볼륨을 생성할 때 기반으로 사용할 이미지 UUID (부팅 볼륨 생성용)")


class VolumeAttachRequest(BaseModel):
    volume_id: str = Field(..., description="연결할 볼륨 UUID")


class VolumeListResponse(BaseModel):
    items: list[VolumeSummary]
