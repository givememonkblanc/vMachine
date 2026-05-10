from datetime import datetime

from pydantic import BaseModel, Field


class MetricValue(BaseModel):
    metric_name: str = Field(description="메트릭 이름 (예: cpu_usage, memory_usage)")
    source: str = Field(description="메트릭 출처 (예: hypervisor-01, openstack)")
    value: float = Field(description="메트릭 값")
    unit: str | None = Field(default=None, description="단위 (예: %, MB, req/s)")
    labels: dict[str, object] | None = Field(default=None, description="메트릭 레이블")
    project_id: str | None = Field(default=None, description="프로젝트 ID")
    resource_id: str | None = Field(default=None, description="리소스 ID")
    recorded_at: datetime | None = Field(default=None, description="기록 시간")


class MetricQueryParams(BaseModel):
    metric_name: str | None = Field(default=None, description="메트릭 이름 필터")
    source: str | None = Field(default=None, description="출처 필터")
    project_id: str | None = Field(default=None, description="프로젝트 ID 필터")
    since: datetime | None = Field(default=None, description="시작 시간")
    until: datetime | None = Field(default=None, description="종료 시간")
    limit: int = Field(default=100, ge=1, le=1000, description="최대 반환 개수")


class MetricListResponse(BaseModel):
    items: list[MetricValue]


class HypervisorUsage(BaseModel):
    hypervisor: str = Field(description="하이퍼바이저 호스트명")
    cpu_usage: float = Field(description="CPU 사용률 (%)")
    memory_usage: float = Field(description="메모리 사용률 (%)")
    memory_total_mb: int = Field(description="전체 메모리 (MB)")
    memory_used_mb: int = Field(description="사용 중인 메모리 (MB)")
    disk_usage: float = Field(description="디스크 사용률 (%)")
    running_vms: int = Field(description="실행 중인 VM 수")


class ProjectUsage(BaseModel):
    project_id: str = Field(description="프로젝트 ID")
    project_name: str | None = Field(default=None, description="프로젝트 이름")
    instance_count: int = Field(description="인스턴스 수")
    total_vcpus: int = Field(description="할당된 vCPU 합계")
    total_ram_mb: int = Field(description="할당된 RAM 합계 (MB)")
    total_disk_gb: int = Field(description="할당된 디스크 합계 (GB)")


class AlertRecordSummary(BaseModel):
    id: str = Field(description="알림 ID")
    severity: str = Field(description="심각도 (critical, warning, info)")
    title: str = Field(description="알림 제목")
    message: str | None = Field(default=None, description="알림 상세 메시지")
    source: str = Field(description="알림 출처")
    resource_type: str | None = Field(default=None, description="관련 리소스 타입")
    resource_id: str | None = Field(default=None, description="관련 리소스 ID")
    status: str = Field(description="상태 (active, resolved)")
    created_at: str | None = Field(default=None, description="생성 시간")
    resolved_at: str | None = Field(default=None, description="해결 시간")


class AlertListResponse(BaseModel):
    items: list[AlertRecordSummary]


class DashboardSummary(BaseModel):
    total_instances: int = Field(description="전체 인스턴스 수")
    active_instances: int = Field(description="실행 중인 인스턴스 수")
    total_hypervisors: int = Field(description="전체 하이퍼바이저 수")
    total_networks: int = Field(description="전체 네트워크 수")
    total_volumes: int = Field(description="전체 볼륨 수")
    active_alerts: int = Field(description="미해결 알림 수")
    total_storage_gb: int = Field(description="전체 스토리지 할당량 (GB)")
    used_storage_gb: int = Field(description="사용 중인 스토리지 (GB)")


class ServiceHealthDetail(BaseModel):
    name: str = Field(description="서비스 이름")
    status: str = Field(description="상태 (ok, degraded, down)")
    latency_ms: float | None = Field(default=None, description="응답 시간 (ms)")
    details: str | None = Field(default=None, description="상세 정보")


class DetailedHealthResponse(BaseModel):
    status: str = Field(description="전체 상태 (ok, degraded, down)")
    services: list[ServiceHealthDetail] = Field(description="개별 서비스 상태 목록")
