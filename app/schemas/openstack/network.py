from pydantic import BaseModel, Field


class NetworkSummary(BaseModel):
    id: str | None = None
    name: str | None = None
    status: str | None = None
    subnets: list[str] = Field(default_factory=list)
    admin_state_up: bool | None = None
    shared: bool | None = None
    is_router_external: bool | None = None


class SubnetSummary(BaseModel):
    id: str | None = None
    name: str | None = None
    cidr: str | None = None
    gateway_ip: str | None = None
    ip_version: int | None = None
    enable_dhcp: bool | None = None
    dns_nameservers: list[str] = Field(default_factory=list)


class NetworkDetail(NetworkSummary):
    subnet_details: list[SubnetSummary] = Field(default_factory=list)


class NetworkCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="생성할 네트워크 이름")
    cidr: str = Field(..., description="서브넷에 할당할 CIDR (예: 10.0.0.0/24)")
    subnet_name: str | None = Field(default=None, description="명시적으로 지정할 서브넷 이름 (기본값: 네트워크이름-subnet)")
    ip_version: int = Field(default=4, ge=4, le=6, description="IP 버전 (4 또는 6)")
    gateway_ip: str | None = Field(default=None, description="기본 게이트웨이 IP 주소 (생략 시 첫 번째 사용가능 IP)")
    enable_dhcp: bool = Field(default=True, description="DHCP 활성화 여부")
    shared: bool = Field(default=False, description="다른 프로젝트와 네트워크 공유 여부")
    admin_state_up: bool = Field(default=True, description="관리자 상태 활성화 여부")
    dns_nameservers: list[str] = Field(default_factory=list, description="할당할 DNS 서버 목록 (예: ['8.8.8.8'])")


class NetworkCreateResponse(BaseModel):
    network_id: str
    subnet_id: str
    name: str
    operation_task_id: str | None = None


class NetworkListResponse(BaseModel):
    items: list[NetworkSummary]
