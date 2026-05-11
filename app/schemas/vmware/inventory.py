from pydantic import BaseModel, Field


class VMDisk(BaseModel):
    label: str = Field(description="디스크 레이블 (예: Hard disk 1)")
    capacity_gb: int = Field(description="디스크 용량 (GB)")
    thin_provisioned: bool = Field(default=True, description="Thin provisioning 여부")
    datastore_name: str | None = Field(
        default=None, description="디스크가 위치한 데이터스토어 이름"
    )
    controller_type: str | None = Field(
        default=None,
        description="디스크 컨트롤러 유형 (lsilogic, pvscsi, sata, nvme 등)",
    )


class VMNic(BaseModel):
    label: str = Field(description="NIC 레이블 (예: Network adapter 1)")
    network_name: str = Field(description="연결된 포트 그룹/네트워크 이름")
    mac_address: str | None = Field(default=None, description="MAC 주소")
    ip_addresses: list[str] = Field(
        default_factory=list, description="할당된 IP 주소 목록"
    )
    nic_type: str | None = Field(
        default=None, description="NIC 유형 (e1000, vmxnet3, vmxnet2, e1000e 등)"
    )


class VMHardware(BaseModel):
    cpu_count: int = Field(description="vCPU 개수")
    cpu_cores_per_socket: int = Field(default=1, description="소켓당 코어 수")
    memory_mb: int = Field(description="메모리 크기 (MB)")
    disks: list[VMDisk] = Field(default_factory=list, description="연결된 디스크 목록")
    nics: list[VMNic] = Field(default_factory=list, description="연결된 NIC 목록")


class VMSummary(BaseModel):
    id: str = Field(description="VMware VM MOR (Managed Object Reference)")
    name: str = Field(description="VM 이름")
    power_state: str = Field(description="전원 상태 (poweredOn, poweredOff, suspended)")
    guest_os: str | None = Field(default=None, description="게스트 OS 전체 문자열")
    hardware: VMHardware | None = Field(default=None, description="하드웨어 사양")
    cluster_name: str | None = Field(default=None, description="소속 클러스터 이름")
    datastores: list[str] = Field(
        default_factory=list, description="사용 중인 데이터스토어 이름 목록"
    )
    tags: list[str] = Field(default_factory=list, description="VM 태그 목록")
    annotation: str | None = Field(default=None, description="VM 설명/주석")
    firmware: str | None = Field(default=None, description="펌웨어 유형 (bios, efi)")
    secure_boot_enabled: bool | None = Field(
        default=None, description="Secure Boot 활성화 여부"
    )
    vmware_tools_status: str | None = Field(
        default=None,
        description="VMware Tools 상태 (toolsOk, toolsNotInstalled, toolsNotRunning 등)",
    )
    disk_controller_types: list[str] | None = Field(
        default=None, description="디스크 컨트롤러 유형 목록"
    )


class DatastoreSummary(BaseModel):
    name: str = Field(description="데이터스토어 이름")
    type: str = Field(description="데이터스토어 유형 (VMFS, NFS, vSAN 등)")
    capacity_gb: float = Field(description="전체 용량 (GB)")
    free_gb: float = Field(description="사용 가능 용량 (GB)")
    accessible: bool = Field(default=True, description="접근 가능 여부")
    maintenance_mode: str = Field(default="normal", description="유지보수 모드 상태")


class NetworkSummary(BaseModel):
    name: str = Field(description="네트워크/포트 그룹 이름")
    type: str = Field(description="유형 (network, distributed, opaque)")
    vlan_id: int | None = Field(default=None, description="VLAN ID")
    accessible: bool = Field(default=True, description="접근 가능 여부")


class InventorySyncResponse(BaseModel):
    synced_vms: int = Field(description="동기화된 VM 수")
    synced_datastores: int = Field(description="동기화된 데이터스토어 수")
    synced_networks: int = Field(description="동기화된 네트워크 수")
    operation_task_id: str | None = None


class VMListResponse(BaseModel):
    items: list[VMSummary]


class DatastoreListResponse(BaseModel):
    items: list[DatastoreSummary]


class NetworkListResponse(BaseModel):
    items: list[NetworkSummary]
