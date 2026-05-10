from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps.services import get_auth_service, get_monitoring_service
from app.core.config.settings import get_settings
from app.schemas.health import HealthResponse, OpenStackHealthResponse
from app.schemas.monitoring import DetailedHealthResponse
from app.services.identity.auth_service import AuthService
from app.services.monitoring.monitoring_service import MonitoringService

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """백엔드 서버 상태 및 구동 환경 확인"""
    settings = get_settings()
    return HealthResponse(status="ok", service=settings.app_name, environment=settings.app_env)


@router.get("/health/openstack", response_model=OpenStackHealthResponse)
def openstack_health(
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> OpenStackHealthResponse:
    """OpenStack 연동 상태 및 인증 유효성 검사"""
    _ = auth_service.validate_connection()
    return OpenStackHealthResponse(status="ok", service="openstack", authenticated=True)


@router.get("/health/detailed", response_model=DetailedHealthResponse)
async def detailed_health(
    monitoring_service: Annotated[MonitoringService, Depends(get_monitoring_service)],
) -> DetailedHealthResponse:
    """API, 데이터베이스 등 개별 서비스의 상세 상태를 한 번에 확인합니다."""
    services = await monitoring_service.get_service_health()
    overall = "ok" if all(s.status == "ok" for s in services) else "degraded"
    return DetailedHealthResponse(status=overall, services=services)
