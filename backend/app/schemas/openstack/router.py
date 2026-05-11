from pydantic import BaseModel, Field


class RouterSummary(BaseModel):
    id: str | None = None
    name: str | None = None
    status: str | None = None
    admin_state_up: bool | None = None
    external_gateway_info: dict[str, object] | None = Field(default=None)


class RouterCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="생성할 라우터 이름")
    admin_state_up: bool = Field(default=True, description="관리자 상태 활성화 여부")
    external_network_id: str | None = Field(default=None, description="외부 게이트웨이로 연결할 네트워크 UUID")


class RouterCreateResponse(BaseModel):
    router_id: str
    name: str
    operation_task_id: str | None = None


class RouterInterfaceRequest(BaseModel):
    subnet_id: str = Field(..., description="라우터 인터페이스로 연결할 서브넷 UUID")


class RouterListResponse(BaseModel):
    items: list[RouterSummary]
