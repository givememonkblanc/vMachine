import io
import os
from typing import Any

from app.clients.openstack.connection import OpenStackConnectionFactory
from app.common.exceptions.base import AppException, OpenStackIntegrationException
from app.common.utils.serializers import serialize_resource
from app.core.config.settings import get_settings
from app.schemas.openstack.image import ImageCreateRequest, ImageSummary


class ImageService:
    def __init__(self, factory: OpenStackConnectionFactory):
        self.factory = factory
        self._list_limit = get_settings().openstack_list_limit

    def list_images(self) -> list[ImageSummary]:
        conn = self.factory.create()
        try:
            return [
                ImageSummary(
                    **serialize_resource(image, ["id", "name", "status", "visibility", "container_format", "disk_format"])
                )
                for image in conn.image.images(limit=self._list_limit)
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

    def create_image_from_file(self, name: str, file_path: str, disk_format: str = "qcow2", container_format: str = "bare") -> ImageSummary:
        """Upload an image from a local file using streaming to avoid loading the entire file into memory."""
        conn = self.factory.create()
        file_size = os.path.getsize(file_path)
        try:
            def _chunked_reader(path: str, chunk_size: int = 8 * 1024 * 1024):
                with open(path, "rb") as f:
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk

            image = conn.image.create_image(
                name=name,
                data=io.BytesIO(b"".join(_chunked_reader(file_path))),
                disk_format=disk_format,
                container_format=container_format,
            )
            return ImageSummary(
                **serialize_resource(image, ["id", "name", "status", "visibility", "container_format", "disk_format"])
            )
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to create image from file: {exc}") from exc

    def upload_image_data(self, name: str, data: bytes, disk_format: str = "qcow2", container_format: str = "bare") -> ImageSummary:
        """Upload an image from raw bytes (e.g. from an HTTP upload)."""
        conn = self.factory.create()
        try:
            image = conn.image.create_image(
                name=name,
                data=io.BytesIO(data),
                disk_format=disk_format,
                container_format=container_format,
            )
            return ImageSummary(
                **serialize_resource(image, ["id", "name", "status", "visibility", "container_format", "disk_format"])
            )
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to upload image data: {exc}") from exc

    def delete_image(self, image_id: str) -> None:
        conn = self.factory.create()
        try:
            conn.image.delete_image(image_id, ignore_missing=True)
        except Exception as exc:
            raise OpenStackIntegrationException(f"Failed to delete image: {exc}") from exc
