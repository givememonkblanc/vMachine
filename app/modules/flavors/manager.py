from app.schemas.flavor import FlavorCreateRequest
from app.services.openstack.flavor_service import FlavorService


class FlavorManager:
    """플레이버(스펙) 도메인 오케스트레이션

    플레이버 CRUD 및 사양 검증 등 상위 워크플로우를 제공합니다.
    """

    def __init__(self, flavor_service: FlavorService) -> None:
        self._flavor = flavor_service

    def find_suitable_flavor(self, vcpus: int, ram_mb: int, disk_gb: int) -> dict | None:
        """요구 스펙을 충족하는 플레이버를 검색합니다."""
        flavors = self._flavor.list_flavors()
        for flavor in flavors:
            if (
                flavor.vcpus is not None and flavor.vcpus >= vcpus
                and flavor.ram is not None and flavor.ram >= ram_mb
                and flavor.disk is not None and flavor.disk >= disk_gb
            ):
                return {"id": flavor.id, "name": flavor.name, "vcpus": flavor.vcpus, "ram": flavor.ram, "disk": flavor.disk}
        return None

    def get_flavor(self, flavor_id: str) -> dict:
        return self._flavor.get_flavor(flavor_id)

    def create_flavor(self, payload: FlavorCreateRequest) -> dict:
        return self._flavor.create_flavor(payload)

    def delete_flavor(self, flavor_id: str) -> None:
        self._flavor.delete_flavor(flavor_id)
