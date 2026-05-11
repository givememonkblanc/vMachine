from pydantic import BaseModel, Field


class SecurityGroupSummary(BaseModel):
    id: str | None = None
    name: str | None = None
    description: str | None = None
    project_id: str | None = None


class SecurityGroupRuleSummary(BaseModel):
    id: str | None = None
    security_group_id: str | None = None
    direction: str | None = None
    ethertype: str | None = None
    protocol: str | None = None
    port_range_min: int | None = None
    port_range_max: int | None = None
    remote_ip_prefix: str | None = None


class SecurityGroupDetail(SecurityGroupSummary):
    rules: list[SecurityGroupRuleSummary] = Field(default_factory=list)


class SecurityGroupCreateRequest(BaseModel):
    name: str = Field(
        ..., min_length=1, max_length=255, description="생성할 보안그룹 이름"
    )
    description: str | None = Field(default=None, description="보안그룹에 대한 설명")


class SecurityGroupRuleCreateRequest(BaseModel):
    direction: str = Field(..., description="방향 (ingress 또는 egress)")
    ethertype: str = Field(default="IPv4", description="이더넷 타입 (IPv4 또는 IPv6)")
    protocol: str | None = Field(
        default=None, description="프로토콜 (tcp, udp, icmp 등)"
    )
    port_range_min: int | None = Field(default=None, description="최소 포트 번호")
    port_range_max: int | None = Field(default=None, description="최대 포트 번호")
    remote_ip_prefix: str | None = Field(
        default=None, description="허용할 대상 IP 대역 (CIDR)"
    )


class SecurityGroupCreateResponse(BaseModel):
    security_group_id: str
    name: str
    operation_task_id: str | None = None


class SecurityGroupRuleCreateResponse(BaseModel):
    rule_id: str
    operation_task_id: str | None = None


class SecurityGroupListResponse(BaseModel):
    items: list[SecurityGroupSummary]
