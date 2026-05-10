from pydantic import BaseModel, Field


class ScalingPolicySummary(BaseModel):
    id: str = Field(description="정책 ID")
    name: str = Field(description="정책 이름")
    metric_name: str = Field(description="모니터링 메트릭 (예: cpu_usage, memory_usage)")
    threshold: float = Field(description="임계값")
    comparison: str = Field(description="비교 방식 (gt: 초과, lt: 미만)")
    min_replicas: int = Field(description="최소 복제본 수")
    max_replicas: int = Field(description="최대 복제본 수")
    cooldown_seconds: int = Field(description="재조정 간 최소 대기 시간")
    target_resource_type: str = Field(description="대상 리소스 유형")
    enabled: bool = Field(description="활성화 여부")
    created_at: str | None = Field(default=None, description="생성 시간")
    operation_task_id: str | None = None


class ScalingPolicyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="정책 이름")
    description: str | None = Field(default=None, description="정책 설명")
    metric_name: str = Field(..., description="모니터링 메트릭")
    threshold: float = Field(..., description="임계값")
    comparison: str = Field(default="gt", description="비교 방식 (gt=초과, lt=미만)")
    min_replicas: int = Field(default=1, ge=1, le=100, description="최소 복제본 수")
    max_replicas: int = Field(default=10, ge=1, le=1000, description="최대 복제본 수")
    cooldown_seconds: int = Field(default=300, ge=60, description="대기 시간(초)")
    target_resource_type: str = Field(default="deployment", description="대상 리소스 유형")
    target_resource_id: str | None = Field(default=None, description="대상 리소스 ID")


class ScalingPolicyListResponse(BaseModel):
    items: list[ScalingPolicySummary]


class ScheduledTaskSummary(BaseModel):
    id: str = Field(description="작업 ID")
    name: str = Field(description="작업 이름")
    task_type: str = Field(description="작업 유형 (backup, health_check, cleanup)")
    cron_expression: str = Field(description="Cron 표현식")
    target_action: str = Field(description="수행할 액션")
    enabled: bool = Field(description="활성화 여부")
    last_run_at: str | None = Field(default=None, description="마지막 실행 시간")
    created_at: str | None = Field(default=None, description="생성 시간")
    operation_task_id: str | None = None


class ScheduledTaskCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="작업 이름")
    description: str | None = Field(default=None, description="작업 설명")
    task_type: str = Field(..., description="작업 유형 (backup, health_check, cleanup, sync)")
    cron_expression: str = Field(..., description="Cron 표현식 (예: 0 3 * * *)")
    target_action: str = Field(..., description="수행할 액션")
    target_resource_type: str | None = Field(default=None, description="대상 리소스 유형")
    target_resource_id: str | None = Field(default=None, description="대상 리소스 ID")


class ScheduledTaskListResponse(BaseModel):
    items: list[ScheduledTaskSummary]


class StoragePoolSummary(BaseModel):
    id: str = Field(description="스토리지 풀 ID")
    name: str = Field(description="스토리지 풀 이름")
    pool_type: str = Field(description="풀 유형 (ceph, nfs, lvm)")
    status: str = Field(description="상태 (active, inactive, error)")
    total_capacity_gb: int = Field(description="전체 용량 (GB)")
    used_capacity_gb: int = Field(description="사용 중인 용량 (GB)")
    replication_factor: int = Field(description="복제 팩터")
    created_at: str | None = Field(default=None, description="생성 시간")
    operation_task_id: str | None = None

    @property
    def available_gb(self) -> int:
        return self.total_capacity_gb - self.used_capacity_gb

    @property
    def usage_percent(self) -> float:
        if self.total_capacity_gb == 0:
            return 0.0
        return round((self.used_capacity_gb / self.total_capacity_gb) * 100, 1)


class StoragePoolCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="스토리지 풀 이름")
    description: str | None = Field(default=None, description="설명")
    pool_type: str = Field(default="ceph", description="풀 유형 (ceph, nfs, lvm)")
    total_capacity_gb: int = Field(default=0, ge=0, description="전체 용량")
    replication_factor: int = Field(default=3, ge=1, le=10, description="복제 팩터")


class StoragePoolListResponse(BaseModel):
    items: list[StoragePoolSummary]
