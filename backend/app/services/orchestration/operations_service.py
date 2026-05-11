import uuid

from sqlalchemy import select

from app.common.exceptions.base import AppException
from app.db.session.session import SessionLocal
from app.models.auto_scaling_policy import AutoScalingPolicy
from app.models.scheduled_task import ScheduledTask
from app.schemas.orchestration.operations_automation import (
    ScalingPolicyCreateRequest,
    ScalingPolicyListResponse,
    ScalingPolicySummary,
    ScheduledTaskCreateRequest,
    ScheduledTaskListResponse,
    ScheduledTaskSummary,
)


class OperationsService:
    async def list_scaling_policies(self) -> ScalingPolicyListResponse:
        async with SessionLocal() as session:
            result = await session.execute(
                select(AutoScalingPolicy).order_by(AutoScalingPolicy.created_at.desc())
            )
            items = [self._serialize_policy(p) for p in result.scalars().all()]
        return ScalingPolicyListResponse(items=items)

    async def get_scaling_policy(self, policy_id: str) -> ScalingPolicySummary:
        async with SessionLocal() as session:
            policy = await session.get(AutoScalingPolicy, uuid.UUID(policy_id))
            if not policy:
                raise AppException(message="Scaling policy not found", status_code=404, error_code="scaling_policy_not_found")
            return self._serialize_policy(policy)

    async def create_scaling_policy(self, payload: ScalingPolicyCreateRequest) -> ScalingPolicySummary:
        async with SessionLocal() as session:
            policy = AutoScalingPolicy(
                name=payload.name,
                description=payload.description,
                metric_name=payload.metric_name,
                threshold=payload.threshold,
                comparison=payload.comparison,
                min_replicas=payload.min_replicas,
                max_replicas=payload.max_replicas,
                cooldown_seconds=payload.cooldown_seconds,
                target_resource_type=payload.target_resource_type,
                target_resource_id=payload.target_resource_id,
            )
            session.add(policy)
            await session.commit()
            await session.refresh(policy)
            return self._serialize_policy(policy)

    async def delete_scaling_policy(self, policy_id: str) -> None:
        async with SessionLocal() as session:
            policy = await session.get(AutoScalingPolicy, uuid.UUID(policy_id))
            if not policy:
                raise AppException(message="Scaling policy not found", status_code=404, error_code="scaling_policy_not_found")
            await session.delete(policy)
            await session.commit()

    async def list_scheduled_tasks(self) -> ScheduledTaskListResponse:
        async with SessionLocal() as session:
            result = await session.execute(
                select(ScheduledTask).order_by(ScheduledTask.created_at.desc())
            )
            items = [self._serialize_task(t) for t in result.scalars().all()]
        return ScheduledTaskListResponse(items=items)

    async def get_scheduled_task(self, task_id: str) -> ScheduledTaskSummary:
        async with SessionLocal() as session:
            task = await session.get(ScheduledTask, uuid.UUID(task_id))
            if not task:
                raise AppException(message="Scheduled task not found", status_code=404, error_code="scheduled_task_not_found")
            return self._serialize_task(task)

    async def create_scheduled_task(self, payload: ScheduledTaskCreateRequest) -> ScheduledTaskSummary:
        async with SessionLocal() as session:
            task = ScheduledTask(
                name=payload.name,
                description=payload.description,
                task_type=payload.task_type,
                cron_expression=payload.cron_expression,
                target_action=payload.target_action,
                target_resource_type=payload.target_resource_type,
                target_resource_id=payload.target_resource_id,
            )
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return self._serialize_task(task)

    async def delete_scheduled_task(self, task_id: str) -> None:
        async with SessionLocal() as session:
            task = await session.get(ScheduledTask, uuid.UUID(task_id))
            if not task:
                raise AppException(message="Scheduled task not found", status_code=404, error_code="scheduled_task_not_found")
            await session.delete(task)
            await session.commit()

    @staticmethod
    def _serialize_policy(p: AutoScalingPolicy) -> ScalingPolicySummary:
        return ScalingPolicySummary(
            id=str(p.id),
            name=p.name,
            metric_name=p.metric_name,
            threshold=p.threshold,
            comparison=p.comparison,
            min_replicas=p.min_replicas,
            max_replicas=p.max_replicas,
            cooldown_seconds=p.cooldown_seconds,
            target_resource_type=p.target_resource_type,
            enabled=p.enabled,
            created_at=p.created_at.isoformat() if p.created_at else None,
        )

    @staticmethod
    def _serialize_task(t: ScheduledTask) -> ScheduledTaskSummary:
        return ScheduledTaskSummary(
            id=str(t.id),
            name=t.name,
            task_type=t.task_type,
            cron_expression=t.cron_expression,
            target_action=t.target_action,
            enabled=t.enabled,
            last_run_at=t.last_run_at.isoformat() if t.last_run_at else None,
            created_at=t.created_at.isoformat() if t.created_at else None,
        )
