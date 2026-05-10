from app.schemas.image import ImageCreateRequest
from app.services.image_service import ImageService


class ImageManager:
    """이미지 도메인 오케스트레이션

    이미지 CRUD 및 가져오기/내보내기 등 상위 워크플로우를 제공합니다.
    """

    def __init__(self, image_service: ImageService) -> None:
        self._image = image_service

    def list_images(self) -> list[dict]:
        return self._image.list_images()

    def get_image(self, image_id: str) -> dict:
        return self._image.get_image(image_id)

    def register_image(self, payload: ImageCreateRequest) -> dict:
        return self._image.create_image(payload)

    def remove_image(self, image_id: str) -> None:
        self._image.delete_image(image_id)
