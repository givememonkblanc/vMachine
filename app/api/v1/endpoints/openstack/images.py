from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps.services import get_image_service, get_operation_task_service
from app.schemas.openstack.image import (
    ImageCreateRequest,
    ImageListResponse,
    ImageSummary,
)
from app.services.core.operation_task_service import OperationTaskService
from app.services.openstack.image_service import ImageService

router = APIRouter()


@router.get("", response_model=ImageListResponse)
def list_images(
    image_service: Annotated[ImageService, Depends(get_image_service)],
) -> ImageListResponse:
    """가상 서버 생성에 사용할 수 있는 이미지(OS 템플릿) 목록 조회"""
    return ImageListResponse(items=image_service.list_images())


@router.get("/{image_id}", response_model=ImageSummary)
def get_image(
    image_id: str,
    image_service: Annotated[ImageService, Depends(get_image_service)],
) -> ImageSummary:
    """특정 이미지의 상세 정보 조회"""
    return image_service.get_image(image_id)


@router.post("", response_model=ImageSummary, status_code=status.HTTP_201_CREATED)
async def create_image(
    payload: ImageCreateRequest,
    image_service: Annotated[ImageService, Depends(get_image_service)],
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> ImageSummary:
    """새로운 이미지 등록 (디스크 포맷, 컨테이너 포맷 등을 지정)"""
    task = await operation_task_service.create_task(
        operation_type="create_image",
        target_type="image",
        target_id=payload.name,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        image = image_service.create_image(payload)
        _ = await operation_task_service.update_task(
            task.id, state="succeeded", target_id=image.id
        )
        return image.model_copy(update={"operation_task_id": task.id})
    except Exception as exc:
        _ = await operation_task_service.update_task(
            task.id, state="failed", error_message=str(exc)
        )
        raise


@router.delete("/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(
    image_id: str,
    image_service: Annotated[ImageService, Depends(get_image_service)],
    operation_task_service: Annotated[
        OperationTaskService, Depends(get_operation_task_service)
    ],
) -> Response:
    """이미지 영구 삭제"""
    task = await operation_task_service.create_task(
        operation_type="delete_image",
        target_type="image",
        target_id=image_id,
    )
    _ = await operation_task_service.update_task(task.id, state="running")

    try:
        image_service.delete_image(image_id)
        _ = await operation_task_service.update_task(
            task.id, state="succeeded", target_id=image_id
        )
    except Exception as exc:
        _ = await operation_task_service.update_task(
            task.id, state="failed", target_id=image_id, error_message=str(exc)
        )
        raise

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["X-Operation-Task-ID"] = task.id
    return response
