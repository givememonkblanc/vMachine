from typing import Literal

from pydantic import BaseModel, Field


class ServerSummary(BaseModel):
    id: str | None = None
    name: str | None = None
    status: str | None = None
    operation_task_id: str | None = None
    flavor_id: str | None = None
    image_id: str | None = None
    created: str | None = None
    key_name: str | None = None
    project_id: str | None = None
    availability_zone: str | None = None
    addresses: dict[str, list[str]] = Field(default_factory=dict)


class ServerDetail(ServerSummary):
    updated: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class ServerCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="생성할 서버 이름")
    image_id: str = Field(..., description="사용할 이미지 UUID")
    flavor_id: str = Field(..., description="사용할 Flavor UUID 또는 이름")
    network_id: str = Field(..., description="연결할 네트워크 UUID")
    key_name: str | None = Field(default=None, description="접속에 사용할 SSH Keypair 이름")
    availability_zone: str | None = Field(default=None, description="배포할 가용 영역 (AZ)")
    metadata: dict[str, str] = Field(default_factory=dict, description="서버에 부여할 메타데이터 (키-값 쌍)")
    wait: bool = Field(default=False, description="서버가 Active 상태가 될 때까지 응답 대기 여부")


class ServerActionRequest(BaseModel):
    action: Literal["start", "stop", "reboot"] = Field(..., description="수행할 액션 (start, stop, reboot 중 하나)")


class VolumeAttachRequest(BaseModel):
    volume_id: str = Field(..., description="연결할 볼륨 UUID")


class ServerResizeRequest(BaseModel):
    flavor_id: str = Field(..., description="변경하고자 하는 대상 Flavor UUID")


class ServerImageCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="생성할 스냅샷 이미지의 이름")


class ServerImageCreateResponse(BaseModel):
    server_id: str
    image_name: str
    operation_task_id: str | None = None


class ServerActionResponse(BaseModel):
    server_id: str
    action: str
    accepted: bool
    operation_task_id: str | None = None


class ServerResizeActionRequest(BaseModel):
    action: Literal["confirm", "revert"] = Field(..., description="Resize 적용(confirm) 또는 취소(revert)")


class ServerListResponse(BaseModel):
    items: list[ServerSummary]
