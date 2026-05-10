import time
import os
import pytest
from app.core.config.settings import Settings
from app.clients.kubernetes.connection import KubernetesClientFactory
from app.services.kubernetes.kubernetes_service import KubernetesService
from app.schemas.kubernetes.kubernetes import DeploymentCreateRequest, DeploymentScaleRequest, ServiceCreateRequest

@pytest.fixture(scope="module")
def k8s_service():
    os.environ["KUBERNETES_KUBECONFIG_PATH"] = os.path.expanduser("~/.kube/config")
    settings = Settings()
    
    assert settings.kubernetes_ready, "KUBERNETES_KUBECONFIG_PATH must be set for this live test"
    
    factory = KubernetesClientFactory(settings)
    return KubernetesService(factory)

@pytest.fixture(scope="module")
def namespace():
    return "default"

def test_k8s_cluster_info(k8s_service):
    """클러스터 노드 정보 조회 테스트"""
    info = k8s_service.get_cluster_info()
    assert info.version is not None
    assert info.node_count > 0

def test_k8s_deployment_lifecycle(k8s_service):
    """Deployment 생성, 스케일, 삭제 라이브 테스트"""
    deployment_name = "test-nginx-dep"
    
    # 1. 생성
    payload = DeploymentCreateRequest(
        name=deployment_name,
        image="nginx:alpine",
        replicas=1,
        ports=[80]
    )
    result = k8s_service.create_deployment(payload)
    assert result.name == deployment_name
    assert result.replicas == 1
    
    # K8s가 파드를 띄울 시간을 줌
    time.sleep(3)
    
    # 2. 조회
    deployments = k8s_service.list_deployments()
    assert any(d.name == deployment_name for d in deployments.items)
    
    # 3. 스케일링
    scale_payload = DeploymentScaleRequest(replicas=2)
    k8s_service.scale_deployment(deployment_name, scale_payload)
    
    time.sleep(2)
    
    # 4. 삭제
    k8s_service.delete_deployment(deployment_name)
    
    time.sleep(2)
    # 삭제되었는지 검증
    deployments = k8s_service.list_deployments()
    assert not any(d.name == deployment_name for d in deployments.items)

def test_k8s_service_lifecycle(k8s_service):
    """Service 생성, 삭제 라이브 테스트"""
    service_name = "test-nginx-svc"
    
    # 1. 생성
    payload = ServiceCreateRequest(
        name=service_name,
        selector={"app": "test-nginx-dep"},
        port=80,
        target_port=80,
        type="ClusterIP"
    )
    result = k8s_service.create_service(payload)
    assert result.name == service_name
    assert result.cluster_ip is not None
    
    # 2. 조회
    services = k8s_service.list_services()
    assert any(s.name == service_name for s in services.items)
    
    # 3. 삭제
    k8s_service.delete_service(service_name)
    
    time.sleep(1)
    services = k8s_service.list_services()
    assert not any(s.name == service_name for s in services.items)
