from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps.services import get_compute_service, get_monitoring_service
from app.schemas.monitoring import (
    AlertListResponse,
    AlertRecordSummary,
    DashboardSummary,
    HypervisorUsage,
    MetricListResponse,
    MetricQueryParams,
    ProjectUsage,
)
from app.services.compute_service import ComputeService
from app.services.monitoring_service import MonitoringService

router = APIRouter()


@router.get("/metrics", response_model=MetricListResponse)
async def query_metrics(
    params: Annotated[MetricQueryParams, Depends()],
    monitoring_service: Annotated[MonitoringService, Depends(get_monitoring_service)],
) -> MetricListResponse:
    """메트릭 데이터를 조건별로 조회합니다. metric_name, source, project_id, 시간 범위로 필터링 가능"""
    return await monitoring_service.query_metrics(
        metric_name=params.metric_name,
        source=params.source,
        project_id=params.project_id,
        since=params.since,
        until=params.until,
        limit=params.limit,
    )


@router.get("/metrics/latest", response_model=MetricListResponse)
async def get_latest_metrics(
    monitoring_service: Annotated[MonitoringService, Depends(get_monitoring_service)],
    source: str | None = None,
) -> MetricListResponse:
    """각 메트릭의 가장 최근 값을 조회합니다. source 필터링 가능"""
    return await monitoring_service.get_latest_metrics(source=source)


@router.get("/hypervisors", response_model=list[HypervisorUsage])
async def get_hypervisor_usage(
    monitoring_service: Annotated[MonitoringService, Depends(get_monitoring_service)],
) -> list[HypervisorUsage]:
    """하이퍼바이저별 CPU/메모리/디스크 사용률 및 실행 중인 VM 수를 조회합니다."""
    return await monitoring_service.get_hypervisor_usage()


@router.get("/projects", response_model=list[ProjectUsage])
async def get_project_usage(
    monitoring_service: Annotated[MonitoringService, Depends(get_monitoring_service)],
) -> list[ProjectUsage]:
    """프로젝트별 리소스 할당 현황(인스턴스/vCPU/RAM/디스크)을 조회합니다."""
    return await monitoring_service.get_project_usage()


@router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    monitoring_service: Annotated[MonitoringService, Depends(get_monitoring_service)],
    status: str | None = None,
    severity: str | None = None,
    limit: int = 50,
) -> AlertListResponse:
    """시스템 알림(Alert) 목록을 조회합니다. 상태와 심각도로 필터링 가능"""
    return await monitoring_service.list_alerts(status=status, severity=severity, limit=limit)


@router.post("/alerts/{alert_id}/resolve", response_model=AlertRecordSummary)
async def resolve_alert(
    alert_id: str,
    monitoring_service: Annotated[MonitoringService, Depends(get_monitoring_service)],
) -> AlertRecordSummary:
    """특정 알림을 해결(Resolve) 처리합니다."""
    return await monitoring_service.resolve_alert(alert_id)


@router.get("/dashboard", response_model=DashboardSummary)
async def get_dashboard(
    monitoring_service: Annotated[MonitoringService, Depends(get_monitoring_service)],
    compute_service: Annotated[ComputeService, Depends(get_compute_service)],
) -> DashboardSummary:
    """대시보드용 통합 리소스 요약 정보를 반환합니다."""
    return await monitoring_service.get_dashboard_summary(compute_service=compute_service)
