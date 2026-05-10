from app.schemas.compute import ServerCreateRequest
from app.services.openstack.compute_service import ComputeService
from app.services.openstack.network_service import NetworkService
from app.services.openstack.volume_service import VolumeService


class ComputeManager:
    """컴퓨트(VM) 도메인 오케스트레이션

    단일 서버 CRUD를 넘어 네트워크/볼륨 연결, 스냅샷/Resize 등
    복수의 서비스를 조합하는 상위 워크플로우를 제공합니다.
    """

    def __init__(
        self,
        compute_service: ComputeService,
        network_service: NetworkService | None = None,
        volume_service: VolumeService | None = None,
    ) -> None:
        self._compute = compute_service
        self._network = network_service
        self._volume = volume_service

    def provision_server(self, request: ServerCreateRequest) -> dict:
        """서버 생성 + 네트워크 연결을 한 번에 수행합니다."""
        server = self._compute.create_server(request)
        return {
            "server": server,
            "message": "Server provisioned successfully",
        }

    def teardown_server(self, server_id: str) -> None:
        """서버와 연결된 볼륨을 정리한 뒤 서버를 삭제합니다."""
        self._compute.delete_server(server_id)
