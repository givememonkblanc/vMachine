from sqlalchemy import Select, select
from uuid import uuid4

from app.db.session.session import SessionLocal
from app.models.audit_log import AuditLog
from app.schemas.audit import AuditLogSummary


async def log_audit_entry(
    actor: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    status: str = "pending",
    request_id: str | None = None,
    payload: dict[str, object] | None = None,
) -> str | None:
    if not action:
        return None

    entry_id = str(uuid4())
    db_entry = AuditLog(
        id=entry_id,
        actor=actor,
        action=action,
        resource_type=resource_type or "unknown",
        resource_id=resource_id,
        status=status,
        request_id=request_id,
        payload=payload,
    )

    async with SessionLocal() as session:
        session.add(db_entry)
        await session.commit()

    return entry_id


class AuditService:
    async def list_audit_logs(
        self,
        limit: int = 50,
        resource_type: str | None = None,
        status: str | None = None,
    ) -> list[AuditLogSummary]:
        query: Select[tuple[AuditLog]] = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)

        if resource_type:
            query = query.where(AuditLog.resource_type == resource_type)
        if status:
            query = query.where(AuditLog.status == status)

        async with SessionLocal() as session:
            result = await session.execute(query)
            entries = result.scalars().all()

        return [
            AuditLogSummary(
                id=entry.id,
                actor=entry.actor,
                action=entry.action,
                resource_type=entry.resource_type,
                resource_id=entry.resource_id,
                status=entry.status,
                request_id=entry.request_id,
                payload=entry.payload,
                created_at=entry.created_at.isoformat() if entry.created_at else None,
            )
            for entry in entries
        ]
