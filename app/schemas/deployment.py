from pydantic import BaseModel, Field


class ClusterSummary(BaseModel):
    id: str = Field(description="클러스터 ID")
    name: str = Field(description="클러스터 이름")
    description: str | None = Field(default=None, description="설명")
    cluster_type: str = Field(description="클러스터 유형 (compute, storage, container)")
    status: str = Field(description="상태 (active, inactive, error)")
    node_count: int = Field(description="노드 수")
    created_at: str | None = Field(default=None, description="생성 시간")
    operation_task_id: str | None = None


class ClusterCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="클러스터 이름")
    description: str | None = Field(default=None, max_length=2000, description="클러스터 설명")
    cluster_type: str = Field(default="compute", description="클러스터 유형 (compute, storage, container)")
    node_count: int = Field(default=0, ge=0, description="초기 노드 수")
    metadata: dict[str, str] = Field(default_factory=dict, description="메타데이터")


class ClusterListResponse(BaseModel):
    items: list[ClusterSummary]


class BatchDeployRequest(BaseModel):
    template_name: str = Field(..., min_length=1, max_length=255, description="배포 템플릿 이름")
    instance_count: int = Field(..., ge=1, le=100, description="배포할 인스턴스 수")
    image_id: str = Field(..., description="사용할 이미지 UUID")
    flavor_id: str = Field(..., description="사용할 Flavor UUID")
    network_id: str = Field(..., description="연결할 네트워크 UUID")
    key_name: str | None = Field(default=None, description="SSH 키페어 이름")
    availability_zone: str | None = Field(default=None, description="가용 영역")


class BatchDeployResponse(BaseModel):
    template_name: str = Field(description="템플릿 이름")
    requested: int = Field(description="요청된 인스턴스 수")
    created: int = Field(description="실제 생성된 인스턴스 수")
    operation_task_id: str | None = None


class MigrationTaskSummary(BaseModel):
    id: str = Field(description="마이그레이션 ID")
    migration_type: str = Field(description="유형 (cold, live, vmware)")
    source_ref: str = Field(description="소스 참조")
    destination_ref: str | None = Field(default=None, description="대상 참조")
    resource_type: str = Field(description="리소스 유형 (server, volume)")
    resource_id: str | None = Field(default=None, description="리소스 ID")
    status: str = Field(description="상태 (queued, running, succeeded, failed)")
    progress: int = Field(description="진행률 (0-100)")
    error_message: str | None = Field(default=None, description="오류 메시지")
    created_at: str | None = Field(default=None, description="생성 시간")
    finished_at: str | None = Field(default=None, description="완료 시간")
    operation_task_id: str | None = None


class MigrationCreateRequest(BaseModel):
    migration_type: str = Field(..., description="마이그레이션 유형 (cold, live, vmware)")
    source_ref: str = Field(..., description="소스 서버/VM 참조")
    destination_ref: str | None = Field(default=None, description="대상 호스트/클러스터 참조")
    resource_type: str = Field(default="server", description="리소스 유형")
    resource_id: str | None = Field(default=None, description="리소스 ID")


class MigrationListResponse(BaseModel):
    items: list[MigrationTaskSummary]
