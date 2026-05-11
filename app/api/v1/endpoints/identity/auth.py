from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps.services import get_auth_service
from app.schemas.identity.auth import (
    OpenStackServiceCatalogResponse,
    OpenStackTokenInfo,
    OpenStackValidationResponse,
)
from app.services.identity.auth_service import AuthService

router = APIRouter()


@router.get("/config", response_model=OpenStackTokenInfo)
def auth_config(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> OpenStackTokenInfo:
    """OpenStack 설정 정보(Auth URL, Region 등) 조회"""
    return auth_service.get_token_info()


@router.post("/validate", response_model=OpenStackValidationResponse)
def validate_openstack(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> OpenStackValidationResponse:
    """현재 설정된 환경변수로 OpenStack 인증(Keystone)이 성공하는지 검증"""
    return auth_service.validate_connection()


@router.get("/session", response_model=OpenStackValidationResponse)
def openstack_session(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> OpenStackValidationResponse:
    """현재 인증된 OpenStack 세션의 토큰 정보, User ID 및 Project ID 상세 조회"""
    return auth_service.validate_connection()


@router.get("/endpoints", response_model=OpenStackServiceCatalogResponse)
def openstack_endpoints(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> OpenStackServiceCatalogResponse:
    """현재 인증된 토큰을 기반으로 OpenStack 서비스 카탈로그(Nova, Neutron 등 API 엔드포인트) 목록 조회"""
    return auth_service.get_service_catalog()
