from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException, OpenStackIntegrationException
from app.common.utils.serializers import serialize_resource
from app.schemas.openstack.image import ImageCreateRequest, ImageSummary


class ImageService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory

    def list_images(self) -> list[ImageSummary]:
        conn = self.factory.create()
        try:
            return [
                ImageSummary(
                    **serialize_resource(image, ["id", "name", "status", "visibility", "container_format", "disk_format"])
                )
                for image in conn.image.images()
            ]
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to list images: {exc}") from exc

    def get_image(self, image_id: str) -> ImageSummary:
        conn = self.factory.create()
        try:
            image = conn.image.get_image(image_id)
            if not image:
                raise AppException(message="Image not found", status_code=404, error_code="image_not_found")
            return ImageSummary(
                **serialize_resource(image, ["id", "name", "status", "visibility", "container_format", "disk_format"])
            )
        except AppException:
            raise
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to get image: {exc}") from exc

    def create_image(self, payload: ImageCreateRequest) -> ImageSummary:
        conn = self.factory.create()
        try:
            image = conn.image.create_image(
                name=payload.name,
                container_format=payload.container_format,
                disk_format=payload.disk_format,
                min_disk=payload.min_disk,
                min_ram=payload.min_ram,
                visibility=payload.visibility,
                protected=payload.protected,
            )
            return ImageSummary(
                **serialize_resource(image, ["id", "name", "status", "visibility", "container_format", "disk_format"])
            )
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to create image: {exc}") from exc

    def delete_image(self, image_id: str) -> None:
        conn = self.factory.create()
        try:
            conn.image.delete_image(image_id, ignore_missing=True)
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to delete image: {exc}") from exc
