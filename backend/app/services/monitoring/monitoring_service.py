import asyncio
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, func, select

from app.common.exceptions.base import AppException
from app.db.session.session import SessionLocal
from app.models.alert_record import AlertRecord
from app.models.monitoring_metric import MetricRecord
from app.schemas.monitoring.monitoring import (
    AlertListResponse,
    AlertRecordSummary,
    DashboardSummary,
    HypervisorUsage,
    MetricListResponse,
    MetricValue,
    ProjectUsage,
    ServiceHealthDetail,
)


# Batch metric queue — accumulates metric writes and flushes periodically
# to avoid one DB INSERT per metric reading.
_METRIC_QUEUE: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
_METRIC_BATCH_SIZE = 50
_METRIC_FLUSH_INTERVAL = 5.0


async def _flush_metric_batch(entries: Sequence[dict[str, Any]]) -> None:
    if not entries:
        return
    async with SessionLocal() as session:
        for entry in entries:
            session.add(MetricRecord(**entry))
        await session.commit()


async def metric_flush_worker() -> None:
    batch: list[dict[str, Any]] = []
    while True:
        try:
            entry = await asyncio.wait_for(_METRIC_QUEUE.get(), timeout=_METRIC_FLUSH_INTERVAL)
            if entry is None:
                break
            batch.append(entry)
            if len(batch) >= _METRIC_BATCH_SIZE:
                await _flush_metric_batch(batch)
                batch.clear()
        except asyncio.TimeoutError:
            if batch:
                await _flush_metric_batch(batch)
                batch.clear()
    if batch:
        await _flush_metric_batch(batch)


async def enqueue_metric_shutdown() -> None:
    await _METRIC_QUEUE.put(None)


class MonitoringService:
    async def record_metric(
        self,
        metric_name: str,
        source: str,
        value: float,
        unit: str | None = None,
        labels: dict[str, object] | None = None,
        project_id: str | None = None,
        resource_id: str | None = None,
    ) -> None:
        await _METRIC_QUEUE.put(
            {
                "metric_name": metric_name,
                "source": source,
                "value": value,
                "unit": unit,
                "labels": labels,
                "project_id": project_id,
                "resource_id": resource_id,
            }
        )

    async def query_metrics(
        self,
        metric_name: str | None = None,
        source: str | None = None,
        project_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> MetricListResponse:
        query: Select[tuple[MetricRecord]] = (
            select(MetricRecord).order_by(MetricRecord.recorded_at.desc()).limit(limit)
        )
        if metric_name:
            query = query.where(MetricRecord.metric_name == metric_name)
        if source:
            query = query.where(MetricRecord.source == source)
        if project_id:
            query = query.where(MetricRecord.project_id == project_id)
        if since:
            query = query.where(MetricRecord.recorded_at >= since)
        if until:
            query = query.where(MetricRecord.recorded_at <= until)

        async with SessionLocal() as session:
            result = await session.execute(query)
            records = result.scalars().all()

        items = [
            MetricValue(
                metric_name=r.metric_name,
                source=r.source,
                value=r.value,
                unit=r.unit,
                labels=r.labels,
                project_id=r.project_id,
                resource_id=r.resource_id,
                recorded_at=r.recorded_at,
            )
            for r in records
        ]
        return MetricListResponse(items=items)

    async def get_latest_metrics(
        self, source: str | None = None
    ) -> MetricListResponse:
        subquery = select(
            MetricRecord.metric_name,
            func.max(MetricRecord.recorded_at).label("max_ts"),
        )
        if source:
            subquery = subquery.where(MetricRecord.source == source)
        subquery = subquery.group_by(MetricRecord.metric_name).subquery()

        query = select(MetricRecord).join(
            subquery,
            (MetricRecord.metric_name == subquery.c.metric_name)
            & (MetricRecord.recorded_at == subquery.c.max_ts),
        )
        if source:
            query = query.where(MetricRecord.source == source)

        async with SessionLocal() as session:
            result = await session.execute(query)
            records = result.scalars().all()

        items = [
            MetricValue(
                metric_name=r.metric_name,
                source=r.source,
                value=r.value,
                unit=r.unit,
                labels=r.labels,
                project_id=r.project_id,
                resource_id=r.resource_id,
                recorded_at=r.recorded_at,
            )
            for r in records
        ]
        return MetricListResponse(items=items)

    async def get_hypervisor_usage(self) -> list[HypervisorUsage]:
        async with SessionLocal() as session:
            cpu_q = await session.execute(
                select(MetricRecord)
                .where(MetricRecord.metric_name == "hypervisor_cpu_usage")
                .order_by(MetricRecord.recorded_at.desc())
                .limit(50)
            )
            cpu_records = cpu_q.scalars().all()

            mem_q = await session.execute(
                select(MetricRecord)
                .where(MetricRecord.metric_name == "hypervisor_memory_usage")
                .order_by(MetricRecord.recorded_at.desc())
                .limit(50)
            )
            mem_records = {r.source: r for r in mem_q.scalars().all()}

            disk_q = await session.execute(
                select(MetricRecord)
                .where(MetricRecord.metric_name == "hypervisor_disk_usage")
                .order_by(MetricRecord.recorded_at.desc())
                .limit(50)
            )
            disk_records = {r.source: r for r in disk_q.scalars().all()}

            vm_q = await session.execute(
                select(MetricRecord)
                .where(MetricRecord.metric_name == "hypervisor_running_vms")
                .order_by(MetricRecord.recorded_at.desc())
                .limit(50)
            )
            vm_records = {r.source: r for r in vm_q.scalars().all()}

        sources = {r.source for r in cpu_records}
        results = []
        for source in sources:
            cpu_r = next((r for r in cpu_records if r.source == source), None)
            mem_r = mem_records.get(source)
            disk_r = disk_records.get(source)
            vm_r = vm_records.get(source)
            results.append(
                HypervisorUsage(
                    hypervisor=source,
                    cpu_usage=cpu_r.value if cpu_r else 0.0,
                    memory_usage=mem_r.value if mem_r else 0.0,
                    memory_total_mb=int(mem_r.labels.get("total_mb", 0)) if mem_r and mem_r.labels else 0,
                    memory_used_mb=int(mem_r.labels.get("used_mb", 0)) if mem_r and mem_r.labels else 0,
                    disk_usage=disk_r.value if disk_r else 0.0,
                    running_vms=int(vm_r.value) if vm_r else 0,
                )
            )
        return results

    async def get_project_usage(self) -> list[ProjectUsage]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(MetricRecord)
                .where(MetricRecord.metric_name.like("project_%"))
                .order_by(MetricRecord.recorded_at.desc())
                .limit(200)
            )
            records = result.scalars().all()

        grouped: dict[str, dict[str, float]] = {}
        for r in records:
            pid = r.project_id or "unknown"
            if pid not in grouped:
                grouped[pid] = {}
            grouped[pid][r.metric_name] = r.value

        return [
            ProjectUsage(
                project_id=pid,
                instance_count=int(m.get("project_instance_count", 0)),
                total_vcpus=int(m.get("project_total_vcpus", 0)),
                total_ram_mb=int(m.get("project_total_ram_mb", 0)),
                total_disk_gb=int(m.get("project_total_disk_gb", 0)),
            )
            for pid, m in grouped.items()
        ]

    async def create_alert(
        self,
        severity: str,
        title: str,
        source: str,
        message: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> AlertRecordSummary:
        async with SessionLocal() as session:
            record = AlertRecord(
                severity=severity,
                title=title,
                message=message,
                source=source,
                resource_type=resource_type,
                resource_id=resource_id,
                status="active",
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
        return self._serialize_alert(record)

    async def list_alerts(
        self,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 50,
    ) -> AlertListResponse:
        query: Select[tuple[AlertRecord]] = (
            select(AlertRecord).order_by(AlertRecord.created_at.desc()).limit(limit)
        )
        if status:
            query = query.where(AlertRecord.status == status)
        if severity:
            query = query.where(AlertRecord.severity == severity)

        async with SessionLocal() as session:
            result = await session.execute(query)
            records = result.scalars().all()

        return AlertListResponse(items=[self._serialize_alert(r) for r in records])

    async def resolve_alert(self, alert_id: str) -> AlertRecordSummary:
        async with SessionLocal() as session:
            record = await session.get(AlertRecord, uuid.UUID(alert_id))
            if not record:
                raise AppException(message="Alert not found", status_code=404, error_code="alert_not_found")
            record.status = "resolved"
            record.resolved_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(record)
        return self._serialize_alert(record)

    async def get_dashboard_summary(
        self, compute_service: object | None = None
    ) -> DashboardSummary:
        async with SessionLocal() as session:
            alert_count_q = await session.execute(
                select(func.count(AlertRecord.id)).where(AlertRecord.status == "active")
            )
            active_alerts = alert_count_q.scalar() or 0

        summary = DashboardSummary(
            total_instances=0,
            active_instances=0,
            total_hypervisors=0,
            total_networks=0,
            total_volumes=0,
            active_alerts=active_alerts,
            total_storage_gb=0,
            used_storage_gb=0,
        )

        if compute_service:
            try:
                servers = compute_service.list_servers()
                summary.total_instances = len(servers)
                summary.active_instances = sum(
                    1 for s in servers if getattr(s, "status", "") == "ACTIVE"
                )
            except Exception:
                pass

        return summary

    async def get_service_health(self) -> list[ServiceHealthDetail]:
        services = [
            ServiceHealthDetail(name="api", status="ok", latency_ms=0.5),
            ServiceHealthDetail(name="database", status="ok", latency_ms=1.2),
        ]
        try:
            async with SessionLocal() as session:
                await session.execute(select(AlertRecord).limit(1))
            services.append(ServiceHealthDetail(name="database", status="ok", latency_ms=1.2))
        except Exception:
            services.append(ServiceHealthDetail(name="database", status="down"))

        return services

    @staticmethod
    def _serialize_alert(record: AlertRecord) -> AlertRecordSummary:
        return AlertRecordSummary(
            id=str(record.id),
            severity=record.severity,
            title=record.title,
            message=record.message,
            source=record.source,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            status=record.status,
            created_at=record.created_at.isoformat() if record.created_at else None,
            resolved_at=record.resolved_at.isoformat() if record.resolved_at else None,
        )
