from app.schemas.kubernetes.kubernetes import (
    DeploymentCreateRequest,
    ServiceCreateRequest,
)
from app.services.kubernetes.kubernetes_service import KubernetesService


class KubernetesManager:
    """Kubernetes 워크로드 통합 오케스트레이션

    Pod/Deployment/Service 개별 CRUD를 넘어
    워크로드 배포, 스케일링, 서비스 노출 등을 복합적으로 처리합니다.
    """

    def __init__(self, kubernetes_service: KubernetesService) -> None:
        self._k8s = kubernetes_service

    def deploy_workload(
        self, name: str, image: str, replicas: int = 1, port: int | None = None
    ) -> dict:
        """Deployment + Service를 한 번에 배포합니다."""
        dep = self._k8s.create_deployment(
            DeploymentCreateRequest(
                name=name, image=image, replicas=replicas, port=port
            )
        )
        svc = self._k8s.create_service(
            ServiceCreateRequest(name=name, port=port or 80, selector={"app": name})
        )
        return {
            "deployment": dep.model_dump(),
            "service": svc.model_dump(),
            "message": "Workload deployed successfully",
        }

    def remove_workload(self, name: str) -> None:
        """Deployment와 연결된 Service를 함께 정리합니다."""
        self._k8s.delete_service(name)
        self._k8s.delete_deployment(name)
