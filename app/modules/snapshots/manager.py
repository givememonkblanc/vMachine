from app.services.openstack.compute_service import ComputeService


class SnapshotManager:
    """스냅샷 도메인 오케스트레이션

    VM 스냅샷 생성 및 백업/복원 워크플로우를 제공합니다.
    """

    def __init__(self, compute_service: ComputeService) -> None:
        self._compute = compute_service

    def create_vm_snapshot(self, server_id: str, snapshot_name: str) -> dict:
        """VM의 현재 상태를 스냅샷 이미지로 생성합니다."""
        image_id = self._compute.create_server_image(server_id, snapshot_name)
        return {
            "server_id": server_id,
            "image_id": image_id,
            "snapshot_name": snapshot_name,
        }

    def resize_server(self, server_id: str, flavor_id: str) -> None:
        """VM의 사양(Flavor)을 변경합니다."""
        self._compute.resize_server(server_id, flavor_id)

    def confirm_resize(self, server_id: str) -> None:
        """사양 변경을 확정합니다."""
        self._compute.confirm_resize(server_id)

    def revert_resize(self, server_id: str) -> None:
        """사양 변경을 취소하고 원래 사양으로 되돌립니다."""
        self._compute.revert_resize(server_id)
