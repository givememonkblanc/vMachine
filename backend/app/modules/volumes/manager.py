from app.schemas.openstack.volume import VolumeCreateRequest
from app.services.openstack.compute_service import ComputeService
from app.services.openstack.volume_service import VolumeService


class VolumeManager:
    """볼륨 도메인 오케스트레이션

    볼륨 CRUD 및 VM 연결/해제 등 상위 워크플로우를 제공합니다.
    """

    def __init__(
        self,
        volume_service: VolumeService,
        compute_service: ComputeService | None = None,
    ) -> None:
        self._volume = volume_service
        self._compute = compute_service

    def provision_volume(self, payload: VolumeCreateRequest) -> dict:
        return self._volume.create_volume(payload)

    def attach_to_server(self, volume_id: str, server_id: str) -> None:
        if self._compute:
            self._compute.attach_volume(server_id, volume_id)

    def detach_from_server(self, volume_id: str, server_id: str) -> None:
        if self._compute:
            self._compute.detach_volume(server_id, volume_id)

    def remove_volume(self, volume_id: str) -> None:
        self._volume.delete_volume(volume_id)

    def list_volumes(self) -> list[dict]:
        return self._volume.list_volumes()

    def get_volume(self, volume_id: str) -> dict:
        return self._volume.get_volume(volume_id)
