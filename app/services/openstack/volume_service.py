from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException
from app.common.utils.openstack_cache import cache_get, cache_invalidate, cache_set
from app.common.utils.serializers import serialize_resource
from app.core.config.settings import get_settings
from app.schemas.openstack.volume import VolumeCreateRequest, VolumeSummary


class VolumeService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory
        self._list_limit = get_settings().openstack_list_limit

    def list_volumes(self) -> list[VolumeSummary]:
        cached = cache_get("volumes")
        if cached is not None:
            return cached
        result = [
            VolumeSummary(**serialize_resource(volume, ["id", "name", "status", "size", "bootable"]))
            for volume in self.factory.call("block_storage", "volumes", limit=self._list_limit)
        ]
        cache_set("volumes", result)
        return result

    def get_volume(self, volume_id: str) -> VolumeSummary:
        volume = self.factory.call("block_storage", "get_volume", volume_id)
        if not volume:
            raise AppException(message="Volume not found", status_code=404, error_code="volume_not_found")
        return VolumeSummary(**serialize_resource(volume, ["id", "name", "status", "size", "bootable"]))

    def delete_volume(self, volume_id: str) -> None:
        deleted = self.factory.call("block_storage", "delete_volume", volume_id, ignore_missing=True)
        if deleted is False:
            raise AppException(message="Volume not found", status_code=404, error_code="volume_not_found")
        cache_invalidate("volumes")

    def create_volume(self, payload: VolumeCreateRequest) -> VolumeSummary:
        volume_args: dict[str, object] = {
            "name": payload.name,
            "size": payload.size,
        }
        if payload.description:
            volume_args["description"] = payload.description
        if payload.image_id:
            volume_args["image"] = payload.image_id

        volume = self.factory.call("block_storage", "create_volume", **volume_args)
        cache_invalidate("volumes")
        return VolumeSummary(**serialize_resource(volume, ["id", "name", "status", "size", "bootable"]))
