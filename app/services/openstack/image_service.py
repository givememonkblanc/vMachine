from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException
from app.common.utils.openstack_cache import cache_get, cache_invalidate, cache_set
from app.common.utils.serializers import serialize_resource
from app.core.config.settings import get_settings
from app.schemas.openstack.image import ImageCreateRequest, ImageSummary


class ImageService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory
        self._list_limit = get_settings().openstack_list_limit

    def list_images(self) -> list[ImageSummary]:
        cached = cache_get("images")
        if cached is not None:
            return cached
        result = [
            ImageSummary(**serialize_resource(image, ["id", "name", "status", "visibility", "size", "created_at"]))
            for image in self.factory.call("image", "images", limit=self._list_limit)
        ]
        cache_set("images", result)
        return result

    def get_image(self, image_id: str) -> ImageSummary:
        image = self.factory.call("image", "get_image", image_id)
        if not image:
            raise AppException(message="Image not found", status_code=404, error_code="image_not_found")
        return ImageSummary(**serialize_resource(image, ["id", "name", "status", "visibility", "size", "created_at"]))

    def create_image(self, payload: ImageCreateRequest) -> ImageSummary:
        kwargs: dict[str, object] = {
            "name": payload.name,
            "disk_format": payload.disk_format or "qcow2",
            "container_format": payload.container_format or "bare",
            "visibility": payload.visibility or "private",
        }
        if payload.tags:
            kwargs["tags"] = payload.tags
        if payload.architecture:
            kwargs["architecture"] = payload.architecture
        if payload.min_disk:
            kwargs["min_disk"] = payload.min_disk
        if payload.min_ram:
            kwargs["min_ram"] = payload.min_ram
        image = self.factory.call("image", "create_image", **kwargs)
        cache_invalidate("images")
        return ImageSummary(**serialize_resource(image, ["id", "name", "status", "visibility", "size", "created_at"]))

    def upload_image_data(self, image_id: str, data: bytes) -> None:
        self.factory.call("image", "upload_image", image_id, data, backend="store")

    def import_image(self, image_id: str, uri: str) -> None:
        self.factory.call("image", "import_image", image_id, method="web-download", uri=uri)

    def delete_image(self, image_id: str) -> None:
        self.factory.call("image", "delete_image", image_id, ignore_missing=True)
        cache_invalidate("images")

