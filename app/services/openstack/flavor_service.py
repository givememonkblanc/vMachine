from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException
from app.core.config.settings import get_settings
from app.schemas.openstack.flavor import FlavorCreateRequest, FlavorSummary


class FlavorService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory
        self._list_limit = get_settings().openstack_list_limit

    def list_flavors(self) -> list[FlavorSummary]:
        return [
            FlavorSummary(
                **{
                    "id": flavor.id,
                    "name": flavor.name,
                    "vcpus": flavor.vcpus,
                    "ram": flavor.ram,
                    "disk": flavor.disk,
                }
            )
            for flavor in self.factory.call(
                "compute", "flavors", limit=self._list_limit
            )
        ]

    def get_flavor(self, flavor_id: str) -> FlavorSummary:
        flavor = self.factory.call("compute", "get_flavor", flavor_id)
        if not flavor:
            raise AppException(
                message="Flavor not found",
                status_code=404,
                error_code="flavor_not_found",
            )
        return FlavorSummary(
            id=flavor.id,
            name=flavor.name,
            vcpus=flavor.vcpus,
            ram=flavor.ram,
            disk=flavor.disk,
        )

    def create_flavor(self, payload: FlavorCreateRequest) -> FlavorSummary:
        flavor = self.factory.call(
            "compute",
            "create_flavor",
            name=payload.name,
            ram=payload.ram,
            vcpus=payload.vcpus,
            disk=payload.disk,
            **(payload.extra_specs or {}),
        )
        return FlavorSummary(
            id=flavor.id,
            name=flavor.name,
            vcpus=flavor.vcpus,
            ram=flavor.ram,
            disk=flavor.disk,
        )

    def delete_flavor(self, flavor_id: str) -> None:
        deleted = self.factory.call(
            "compute", "delete_flavor", flavor_id, ignore_missing=True
        )
        if deleted is False:
            raise AppException(
                message="Flavor not found",
                status_code=404,
                error_code="flavor_not_found",
            )
