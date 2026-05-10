from app.services.audit_service import AuditService
from app.services.compute_service import ComputeService
from app.services.image_service import ImageService
from app.services.network_service import NetworkService


class HealthManager:
    """헬스 체크 도메인 오케스트레이션

    개별 서비스 상태를 종합하여 시스템 전반의 헬스 체크를 제공합니다.
    """

    def __init__(
        self,
        compute_service: ComputeService | None = None,
        network_service: NetworkService | None = None,
        image_service: ImageService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self._compute = compute_service
        self._network = network_service
        self._image = image_service
        self._audit = audit_service

    def check_all(self) -> dict:
        """모든 의존 서비스의 상태를 진단합니다."""
        status: dict[str, str] = {}
        if self._compute:
            try:
                self._compute.list_servers()
                status["compute"] = "ok"
            except Exception:
                status["compute"] = "unreachable"
        if self._network:
            try:
                self._network.list_networks()
                status["network"] = "ok"
            except Exception:
                status["network"] = "unreachable"
        if self._image:
            try:
                self._image.list_images()
                status["image"] = "ok"
            except Exception:
                status["image"] = "unreachable"
        return status
