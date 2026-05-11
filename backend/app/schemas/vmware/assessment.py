from pydantic import BaseModel, Field


class FlavorMatchResult(BaseModel):
    flavor_id: str = Field(description="매칭된 OpenStack Flavor ID")
    flavor_name: str = Field(description="매칭된 Flavor 이름")
    score: float = Field(ge=0.0, le=1.0, description="유사도 점수 (1.0 = 완벽 일치)")
    vcpus: int = Field(description="Flavor vCPU 수")
    ram: int = Field(description="Flavor RAM 크기 (MB)")
    disk: int = Field(description="Flavor 디스크 크기 (GB)")
    overprovisioned: bool = Field(default=False, description="VM 사양이 Flavor보다 낮음 (리소스 낭비)")
    underprovisioned: bool = Field(default=False, description="VM 사양이 Flavor보다 높음 (성능 부족 위험)")


class NetworkMappingResult(BaseModel):
    vm_network: str = Field(description="VMware 네트워크/포트 그룹 이름")
    openstack_network_id: str | None = Field(default=None, description="매칭된 OpenStack 네트워크 UUID")
    openstack_network_name: str | None = Field(default=None, description="매칭된 OpenStack 네트워크 이름")
    match_type: str = Field(description="매칭 방식 (exact_name, case_insensitive, vlan_id, cidr, not_found)")
    confidence: float = Field(ge=0.0, le=1.0, description="매칭 신뢰도")


class DiskMappingResult(BaseModel):
    vm_disk_label: str = Field(description="VMware 디스크 레이블")
    vm_disk_gb: int = Field(description="VMware 디스크 용량 (GB)")
    openstack_volume_type: str | None = Field(default=None, description="추천 OpenStack 볼륨 타입")
    openstack_size_gb: int = Field(description="추천 OpenStack 볼륨 크기 (GB)")
    bootable: bool = Field(default=False, description="부트 가능 디스크 여부")


class VMCompatibilityResult(BaseModel):
    vm_id: str = Field(description="VMware VM MOR")
    vm_name: str = Field(description="VM 이름")
    compatible: bool = Field(description="전체 마이그레이션 호환 여부")
    power_state: str = Field(description="현재 전원 상태")
    os_supported: bool = Field(description="게스트 OS 지원 여부")
    cpu_compatible: bool = Field(description="CPU 호환 여부")
    memory_compatible: bool = Field(description="메모리 호환 여부")
    disk_compatible: bool = Field(description="디스크 호환 여부")
    network_compatible: bool = Field(description="네트워크 호환 여부")
    issues: list[str] = Field(default_factory=list, description="발견된 호환성 문제 목록")
    warnings: list[str] = Field(default_factory=list, description="경고 사항 목록")


class VMMappingResult(BaseModel):
    vm_id: str = Field(description="VMware VM MOR")
    vm_name: str = Field(description="VM 이름")
    flavor_match: FlavorMatchResult | None = Field(default=None, description="매칭된 Flavor")
    network_mappings: list[NetworkMappingResult] = Field(default_factory=list, description="네트워크 매핑 결과")
    disk_mappings: list[DiskMappingResult] = Field(default_factory=list, description="디스크 매핑 결과")


class AssessmentRequest(BaseModel):
    vm_ids: list[str] = Field(..., min_length=1, description="평가할 VMware VM MOR 목록")
    include_mapping: bool = Field(default=True, description="OpenStack 리소스 매핑 포함 여부")


class AssessmentResult(BaseModel):
    vm_id: str = Field(description="VMware VM MOR")
    vm_name: str = Field(description="VM 이름")
    compatibility: VMCompatibilityResult = Field(description="호환성 평가 결과")
    mapping: VMMappingResult | None = Field(default=None, description="리소스 매핑 결과")


class AssessmentResponse(BaseModel):
    assessments: list[AssessmentResult] = Field(description="VM별 평가 결과 목록")
    summary: dict[str, int] = Field(description="요약 통계 (total, compatible, incompatible, warning_count)")
    operation_task_id: str | None = None


class MigrationStep(BaseModel):
    order: int = Field(description="실행 순서")
    action: str = Field(description="액션 유형 (create_flavor, create_network, create_volume, import_image, create_server, cleanup)")
    description: str = Field(description="단계 설명")
    resource_id: str | None = Field(default=None, description="대상 리소스 ID")
    estimated_minutes: int = Field(default=5, description="예상 소요 시간 (분)")


class MigrationPlanVM(BaseModel):
    vm_id: str = Field(description="VMware VM MOR")
    vm_name: str = Field(description="VM 이름")
    priority: int = Field(default=5, ge=1, le=10, description="마이그레이션 우선순위 (1=가장 높음)")
    target_flavor_id: str | None = Field(default=None, description="대상 OpenStack Flavor ID")
    target_network_ids: list[str] = Field(default_factory=list, description="대상 OpenStack 네트워크 UUID 목록")
    target_volume_types: list[str] = Field(default_factory=list, description="대상 볼륨 타입 목록")
    estimated_downtime_minutes: int = Field(default=0, description="예상 다운타임 (분)")
    steps: list[MigrationStep] = Field(default_factory=list, description="실행 단계 목록")
    estimated_total_minutes: int = Field(default=0, description="전체 예상 소요 시간 (분)")


class MigrationPlanRequest(BaseModel):
    vm_ids: list[str] = Field(..., min_length=1, description="마이그레이션 계획을 수립할 VM 목록")
    priority_overrides: dict[str, int] = Field(default_factory=dict, description="VM별 우선순위 오버라이드")


class MigrationPlanResponse(BaseModel):
    plan_id: str = Field(description="계획 ID")
    vms: list[MigrationPlanVM] = Field(description="VM별 마이그레이션 계획")
    total_vms: int = Field(description="계획에 포함된 전체 VM 수")
    total_estimated_minutes: int = Field(description="전체 예상 소요 시간 (분)")
    created_at: str = Field(description="계획 생성 시간")
    operation_task_id: str | None = None
