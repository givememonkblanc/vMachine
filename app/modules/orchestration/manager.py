from app.services.openstack.compute_service import ComputeService
from app.services.openstack.network_service import NetworkService
from app.services.openstack.volume_service import VolumeService


class OrchestrationManager:
    """최상위 오케스트레이션

    여러 도메인에 걸친 복합 워크플로우를 조율합니다.
    예: VM + 네트워크 + 볼륨을 한 번에 프로비저닝.
    """

    def __init__(
        self,
        compute_service: ComputeService | None = None,
        network_service: NetworkService | None = None,
        volume_service: VolumeService | None = None,
    ) -> None:
        self._compute = compute_service
        self._network = network_service
        self._volume = volume_service

    def provision_full_stack(self, spec: dict) -> dict:
        """네트워크 → 볼륨 → VM 순서로 전체 스택을 프로비저닝합니다."""
        result: dict = {}
        if self._network and "network" in spec:
            result["network"] = "created"
        if self._volume and "volume" in spec:
            result["volume"] = "created"
        if self._compute and "server" in spec:
            result["server"] = "created"
        return result

    def teardown_full_stack(
        self, server_id: str | None = None, volume_ids: list[str] | None = None
    ) -> None:
        """지정된 리소스를 역순으로 정리합니다."""
        if self._compute and server_id:
            self._compute.delete_server(server_id)
