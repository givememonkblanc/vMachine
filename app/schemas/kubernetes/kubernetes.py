from pydantic import BaseModel, Field


class ContainerSummary(BaseModel):
    name: str
    image: str
    ports: list[int] = Field(default_factory=list)


class PodSummary(BaseModel):
    name: str = Field(description="Pod 이름")
    namespace: str = Field(description="Namespace")
    status: str = Field(description="Pod 상태 (Running, Pending, Succeeded, Failed, Unknown)")
    node: str | None = Field(default=None, description="할당된 노드")
    pod_ip: str | None = Field(default=None, description="Pod IP 주소")
    created: str | None = Field(default=None, description="생성 시간")
    containers: list[ContainerSummary] = Field(default_factory=list, description="컨테이너 목록")
    labels: dict[str, str] = Field(default_factory=dict, description="레이블")
    operation_task_id: str | None = None


class PodCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=253, description="Pod 이름")
    image: str = Field(..., description="컨테이너 이미지 (예: nginx:latest)")
    namespace: str = Field(default="default", description="대상 Namespace")
    port: int | None = Field(default=None, ge=1, le=65535, description="컨테이너 노출 포트")
    labels: dict[str, str] = Field(default_factory=dict, description="레이블")
    replicas: int = Field(default=1, ge=1, le=100, description="복제본 수")


class PodListResponse(BaseModel):
    items: list[PodSummary]


class DeploymentSummary(BaseModel):
    name: str = Field(description="Deployment 이름")
    namespace: str = Field(description="Namespace")
    replicas: int = Field(description="설정 복제본 수")
    ready_replicas: int = Field(description="준비된 복제본 수")
    available_replicas: int = Field(description="사용 가능한 복제본 수")
    strategy: str = Field(default="RollingUpdate", description="업데이트 전략")
    created: str | None = Field(default=None, description="생성 시간")
    operation_task_id: str | None = None


class DeploymentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=253, description="Deployment 이름")
    image: str = Field(..., description="컨테이너 이미지")
    namespace: str = Field(default="default", description="대상 Namespace")
    replicas: int = Field(default=1, ge=1, le=100, description="복제본 수")
    port: int | None = Field(default=None, ge=1, le=65535, description="컨테이너 노출 포트")
    labels: dict[str, str] = Field(default_factory=dict, description="레이블")


class DeploymentScaleRequest(BaseModel):
    replicas: int = Field(..., ge=0, le=1000, description="변경할 복제본 수")


class DeploymentListResponse(BaseModel):
    items: list[DeploymentSummary]


class ServiceSummary(BaseModel):
    name: str = Field(description="Service 이름")
    namespace: str = Field(description="Namespace")
    type: str = Field(default="ClusterIP", description="Service 타입 (ClusterIP, NodePort, LoadBalancer)")
    cluster_ip: str | None = Field(default=None, description="Cluster IP 주소")
    ports: list[dict] = Field(default_factory=list, description="노출 포트 목록")
    created: str | None = Field(default=None, description="생성 시간")
    operation_task_id: str | None = None


class ServiceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=253, description="Service 이름")
    namespace: str = Field(default="default", description="대상 Namespace")
    type: str = Field(default="ClusterIP", description="Service 타입 (ClusterIP, NodePort, LoadBalancer)")
    port: int = Field(..., ge=1, le=65535, description="Service 포트")
    target_port: int | None = Field(default=None, ge=1, le=65535, description="대상 컨테이너 포트 (기본값: port)")
    selector: dict[str, str] = Field(default_factory=dict, description="Pod 선택자 레이블")


class ServiceListResponse(BaseModel):
    items: list[ServiceSummary]


class K8sClusterInfo(BaseModel):
    node_count: int = Field(description="노드 수")
    namespaces: list[str] = Field(default_factory=list, description="Namespace 목록")
    version: str | None = Field(default=None, description="Kubernetes 버전")
