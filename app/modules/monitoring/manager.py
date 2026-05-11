from app.services.monitoring.monitoring_service import MonitoringService
from app.services.openstack.compute_service import ComputeService
from app.services.openstack.network_service import NetworkService
from app.services.openstack.volume_service import VolumeService


class MonitorManager:
    """모니터링 도메인 오케스트레이션

    리소스 사용량, 이벤트 수집 등 관측/알림 워크플로우를 제공합니다.
    """

    def __init__(
        self,
        compute_service: ComputeService | None = None,
        network_service: NetworkService | None = None,
        volume_service: VolumeService | None = None,
        monitoring_service: MonitoringService | None = None,
    ) -> None:
        self._compute = compute_service
        self._network = network_service
        self._volume = volume_service
        self._monitoring = monitoring_service

    async def collect_hypervisor_metrics(self) -> int:
        """OpenStack 하이퍼바이저로부터 메트릭을 수집하여 저장합니다."""
        if not self._compute or not self._monitoring:
            return 0

        try:
            servers = self._compute.list_servers()
            await self._monitoring.record_metric(
                metric_name="total_instances",
                source="openstack",
                value=len(servers),
                unit="count",
            )
            return len(servers)
        except Exception:
            return -1

    async def get_resource_summary(self) -> dict:
        """전체 리소스 사용 현황 요약을 반환합니다."""
        summary: dict = {"servers": 0, "networks": 0, "volumes": 0}
        if self._compute:
            try:
                servers = self._compute.list_servers()
                summary["servers"] = len(servers)
            except Exception:
                summary["servers"] = -1
        return summary
