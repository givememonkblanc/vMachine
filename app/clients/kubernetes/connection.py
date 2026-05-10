from typing import Any

from app.common.exceptions.base import AppException
from app.core.config.settings import Settings


class KubernetesClientFactory:
    """Kubernetes API 클라이언트 팩토리

    kubeconfig 파일 또는 in-cluster 구성을 기반으로
    kubernetes.client의 API 인스턴스를 생성합니다.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_core_api(self) -> object:
        """CoreV1Api 인스턴스를 반환합니다."""
        return self._get_api("CoreV1Api")

    def create_apps_api(self) -> object:
        """AppsV1Api 인스턴스를 반환합니다."""
        return self._get_api("AppsV1Api")

    def _get_api(self, api_name: str) -> object:
        if not self.settings.kubernetes_ready:
            raise AppException(
                message="Kubernetes settings are incomplete. Set KUBERNETES_KUBECONFIG_PATH or KUBERNETES_IN_CLUSTER.",
                status_code=503,
                error_code="kubernetes_not_configured",
            )

        try:
            import kubernetes.config as k8s_config
            import kubernetes.client as k8s_client

            if self.settings.kubernetes_in_cluster:
                k8s_config.load_incluster_config()
            else:
                k8s_config.load_kube_config(config_file=self.settings.kubernetes_kubeconfig_path)

            api_class = getattr(k8s_client, api_name)
            return api_class()
        except AppException:
            raise
        except Exception as exc:
            raise AppException(
                message=f"Failed to initialize Kubernetes {api_name}: {exc}",
                status_code=503,
                error_code="kubernetes_client_error",
            ) from exc
