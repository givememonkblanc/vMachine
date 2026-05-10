from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException, OpenStackIntegrationException
from app.common.utils.serializers import serialize_resource
from app.core.config.settings import get_settings
from app.schemas.openstack.flavor import FlavorCreateRequest, FlavorSummary


class FlavorService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory
        self._list_limit = get_settings().openstack_list_limit

    def list_flavors(self) -> list[FlavorSummary]:
        conn = self.factory.create()
        try:
            return [
                FlavorSummary(**serialize_resource(flavor, ["id", "name", "vcpus", "ram", "disk"]))
                for flavor in conn.compute.flavors(limit=self._list_limit)
            ]
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to list flavors: {exc}") from exc

    def get_flavor(self, flavor_id: str) -> FlavorSummary:
        conn = self.factory.create()
        try:
            flavor = conn.compute.get_flavor(flavor_id)
            if not flavor:
                raise AppException(message="Flavor not found", status_code=404, error_code="flavor_not_found")
            return FlavorSummary(**serialize_resource(flavor, ["id", "name", "vcpus", "ram", "disk"]))
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to get flavor: {exc}") from exc

    def create_flavor(self, payload: FlavorCreateRequest) -> FlavorSummary:
        conn = self.factory.create()
        try:
            flavor = conn.compute.create_flavor(
                name=payload.name,
                vcpus=payload.vcpus,
                ram=payload.ram,
                disk=payload.disk,
            )
            return FlavorSummary(**serialize_resource(flavor, ["id", "name", "vcpus", "ram", "disk"]))
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to create flavor: {exc}") from exc

    def delete_flavor(self, flavor_id: str) -> None:
        conn = self.factory.create()
        try:
            deleted = conn.compute.delete_flavor(flavor_id, ignore_missing=True)
            if deleted is False:
                raise AppException(message="Flavor not found", status_code=404, error_code="flavor_not_found")
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to delete flavor: {exc}") from exc
