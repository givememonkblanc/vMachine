from datetime import datetime, timezone

from sqlalchemy import select

from app.db.session.session import SessionLocal
from app.models.migration_assessment import MigrationAssessment, MigrationPlan
from app.schemas.vmware.assessment import (
    PersistedAssessmentDetail,
    PersistedAssessmentSummary,
    PersistedPlanDetail,
    PersistedPlanSummary,
)


class AssessmentPersistenceService:
    """CRUD for persisted migration assessment and plan records."""

    @staticmethod
    async def save_assessment(
        vm_id: str,
        vm_name: str,
        compatible: bool,
        compatibility_score: float,
        vm_power_state: str | None = None,
        vm_guest_os: str | None = None,
        compatibility_detail: dict | None = None,
        flavor_match: dict | None = None,
        network_mappings: dict | None = None,
        disk_mappings: dict | None = None,
        mapping_score: float = 0.0,
        source_vm_metadata: dict | None = None,
        issues: list[str] | None = None,
        warnings: list[str] | None = None,
        ttl_minutes: int = 1440,
    ) -> MigrationAssessment:
        async with SessionLocal() as session:
            expires_at = datetime.now(timezone.utc)
            try:
                expires_at = expires_at.replace(
                    hour=23, minute=59, second=0, microsecond=0
                )
            except ValueError:
                pass

            record = MigrationAssessment(
                vm_id=vm_id,
                vm_name=vm_name,
                compatible=compatible,
                compatibility_score=compatibility_score,
                vm_power_state=vm_power_state,
                vm_guest_os=vm_guest_os,
                compatibility_detail=compatibility_detail,
                flavor_match=flavor_match,
                network_mappings=network_mappings,
                disk_mappings=disk_mappings,
                mapping_score=mapping_score,
                source_vm_metadata=source_vm_metadata,
                issues=issues,
                warnings=warnings,
                expires_at=expires_at,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    @staticmethod
    async def save_plan(
        assessment_id: str,
        vm_id: str,
        priority: int = 5,
        target_flavor_id: str | None = None,
        target_flavor_name: str | None = None,
        target_network_ids: dict | None = None,
        target_volume_types: dict | None = None,
        estimated_downtime_minutes: int = 0,
        estimated_total_minutes: int = 0,
        steps: dict | None = None,
        notes: str | None = None,
    ) -> MigrationPlan:
        async with SessionLocal() as session:
            record = MigrationPlan(
                assessment_id=assessment_id,
                vm_id=vm_id,
                priority=priority,
                target_flavor_id=target_flavor_id,
                target_flavor_name=target_flavor_name,
                target_network_ids=target_network_ids,
                target_volume_types=target_volume_types,
                estimated_downtime_minutes=estimated_downtime_minutes,
                estimated_total_minutes=estimated_total_minutes,
                steps=steps,
                notes=notes,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record

    @staticmethod
    async def get_assessment(assessment_id: str) -> PersistedAssessmentDetail | None:
        async with SessionLocal() as session:
            stmt = select(MigrationAssessment).where(
                MigrationAssessment.id == assessment_id
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if not record:
                return None
            return AssessmentPersistenceService._to_detail(record)

    @staticmethod
    async def get_plan(plan_id: str) -> PersistedPlanDetail | None:
        async with SessionLocal() as session:
            stmt = select(MigrationPlan).where(MigrationPlan.id == plan_id)
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if not record:
                return None
            return AssessmentPersistenceService._to_plan_detail(record)

    @staticmethod
    async def list_assessments(
        limit: int = 20, offset: int = 0, compatible_only: bool | None = None
    ) -> list[PersistedAssessmentSummary]:
        async with SessionLocal() as session:
            stmt = select(MigrationAssessment).order_by(
                MigrationAssessment.assessed_at.desc()
            )
            if compatible_only is not None:
                stmt = stmt.where(MigrationAssessment.compatible == compatible_only)
            stmt = stmt.offset(offset).limit(limit)
            result = await session.execute(stmt)
            records = result.scalars().all()
            return [
                PersistedAssessmentSummary(
                    id=r.id,
                    vm_id=r.vm_id,
                    vm_name=r.vm_name,
                    compatible=r.compatible,
                    score=r.compatibility_score,
                    assessed_at=r.assessed_at.isoformat() if r.assessed_at else "",
                )
                for r in records
            ]

    @staticmethod
    async def list_plans(
        assessment_id: str | None = None, limit: int = 20, offset: int = 0
    ) -> list[PersistedPlanSummary]:
        async with SessionLocal() as session:
            stmt = select(MigrationPlan).order_by(MigrationPlan.created_at.desc())
            if assessment_id:
                stmt = stmt.where(MigrationPlan.assessment_id == assessment_id)
            stmt = stmt.offset(offset).limit(limit)
            result = await session.execute(stmt)
            records = result.scalars().all()
            return [
                PersistedPlanSummary(
                    id=r.id,
                    vm_id=r.vm_id,
                    priority=r.priority,
                    status=r.status,
                    estimated_total_minutes=r.estimated_total_minutes,
                    created_at=r.created_at.isoformat() if r.created_at else "",
                )
                for r in records
            ]

    @staticmethod
    async def delete_assessment(assessment_id: str) -> bool:
        async with SessionLocal() as session:
            stmt = select(MigrationAssessment).where(
                MigrationAssessment.id == assessment_id
            )
            result = await session.execute(stmt)
            record = result.scalar_one_or_none()
            if not record:
                return False
            await session.delete(record)
            await session.commit()
            return True

    @staticmethod
    def _to_detail(record: MigrationAssessment) -> PersistedAssessmentDetail:
        plans = [
            PersistedPlanSummary(
                id=p.id,
                vm_id=p.vm_id,
                priority=p.priority,
                status=p.status,
                estimated_total_minutes=p.estimated_total_minutes,
                created_at=p.created_at.isoformat() if p.created_at else "",
            )
            for p in (record.plans or [])
        ]
        return PersistedAssessmentDetail(
            id=record.id,
            vm_id=record.vm_id,
            vm_name=record.vm_name,
            compatible=record.compatible,
            score=record.compatibility_score,
            assessed_at=record.assessed_at.isoformat() if record.assessed_at else "",
            compatibility_detail=record.compatibility_detail,
            flavor_match=record.flavor_match,
            network_mappings=record.network_mappings,
            disk_mappings=record.disk_mappings,
            source_vm_metadata=record.source_vm_metadata,
            issues=record.issues,
            warnings=record.warnings,
            plans=plans,
        )

    @staticmethod
    def _to_plan_detail(record: MigrationPlan) -> PersistedPlanDetail:
        assessment = None
        if record.assessment:
            a = record.assessment
            assessment = PersistedAssessmentSummary(
                id=a.id,
                vm_id=a.vm_id,
                vm_name=a.vm_name,
                compatible=a.compatible,
                score=a.compatibility_score,
                assessed_at=a.assessed_at.isoformat() if a.assessed_at else "",
            )
        return PersistedPlanDetail(
            id=record.id,
            vm_id=record.vm_id,
            priority=record.priority,
            status=record.status,
            estimated_total_minutes=record.estimated_total_minutes,
            created_at=record.created_at.isoformat() if record.created_at else "",
            assessment_id=record.assessment_id,
            target_flavor_id=record.target_flavor_id,
            target_flavor_name=record.target_flavor_name,
            target_network_ids=record.target_network_ids,
            target_volume_types=record.target_volume_types,
            estimated_downtime_minutes=record.estimated_downtime_minutes,
            steps=record.steps,
            notes=record.notes,
            updated_at=record.updated_at.isoformat() if record.updated_at else "",
            assessment=assessment,
        )


__all__ = ["AssessmentPersistenceService"]
