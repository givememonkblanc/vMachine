from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException, OpenStackIntegrationException
from app.common.utils.serializers import serialize_resource
from app.schemas.openstack.volume import VolumeCreateRequest, VolumeSummary


class VolumeService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory

    def list_volumes(self) -> list[VolumeSummary]:
        conn = self.factory.create()
        try:
            return [
                VolumeSummary(**serialize_resource(volume, ["id", "name", "status", "size", "bootable"]))
                for volume in conn.block_storage.volumes()
            ]
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to list volumes: {exc}") from exc

    def get_volume(self, volume_id: str) -> VolumeSummary:
        conn = self.factory.create()
        try:
            volume = conn.block_storage.get_volume(volume_id)
            if not volume:
                raise AppException(message="Volume not found", status_code=404, error_code="volume_not_found")
            return VolumeSummary(**serialize_resource(volume, ["id", "name", "status", "size", "bootable"]))
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to get volume: {exc}") from exc

    def delete_volume(self, volume_id: str) -> None:
        conn = self.factory.create()
        try:
            deleted = conn.block_storage.delete_volume(volume_id, ignore_missing=True)
            if deleted is False:
                raise AppException(message="Volume not found", status_code=404, error_code="volume_not_found")
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to delete volume: {exc}") from exc

    def create_volume(self, payload: VolumeCreateRequest) -> VolumeSummary:
        conn = self.factory.create()
        volume_args = {
            "name": payload.name,
            "size": payload.size,
        }
        if payload.description:
            volume_args["description"] = payload.description
        if payload.image_id:
            volume_args["image"] = payload.image_id

        try:
            volume = conn.block_storage.create_volume(**volume_args)
            return VolumeSummary(**serialize_resource(volume, ["id", "name", "status", "size", "bootable"]))
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to create volume: {exc}") from exc
