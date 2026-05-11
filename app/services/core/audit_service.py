import asyncio
from asyncio import Queue
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, select

from app.db.session.session import SessionLocal
from app.models.audit_log import AuditLog
from app.schemas.core.audit import AuditLogSummary

# ---------------------------------------------------------------------------
# Batch audit queue — accumulates entries and flushes them periodically
# or when the batch reaches a threshold, avoiding one DB write per request.
# ---------------------------------------------------------------------------

_AUDIT_QUEUE: Queue[dict[str, Any] | None] = Queue()
_BATCH_SIZE = 20
_FLUSH_INTERVAL = 2.0  # seconds


def _make_entry(
    actor: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    status: str = "pending",
    request_id: str | None = None,
    payload: dict[str, object] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "actor": actor,
        "action": action,
        "resource_type": resource_type or "unknown",
        "resource_id": resource_id,
        "status": status,
        "request_id": request_id,
        "payload": payload,
    }


async def enqueue_audit_entry(
    actor: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    status: str = "pending",
    request_id: str | None = None,
    payload: dict[str, object] | None = None,
) -> None:
    """Push an audit entry onto the async queue for batch persistence.

    Returns immediately — the actual DB INSERT happens in the background
    flush worker.  If the action is missing the entry is silently dropped.
    """
    if not action:
        return
    await _AUDIT_QUEUE.put(
        _make_entry(
            actor, action, resource_type, resource_id, status, request_id, payload
        )
    )


async def log_audit_entry(
    actor: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    status: str = "pending",
    request_id: str | None = None,
    payload: dict[str, object] | None = None,
) -> str | None:
    """Direct synchronous write (legacy path — prefer enqueue_audit_entry).

    Used when callers need the entry ID returned immediately.
    """
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


async def _flush_batch(entries: list[dict[str, Any]]) -> None:
    """Persist a batch of audit entries in a single transaction."""
    if not entries:
        return
    async with SessionLocal() as session:
        for entry in entries:
            session.add(AuditLog(**entry))
        await session.commit()


async def audit_flush_worker() -> None:
    """Background task: drain the audit queue in batches.

    Flushes whenever the queue reaches ``_BATCH_SIZE`` entries or
    ``_FLUSH_INTERVAL`` seconds have elapsed since the last flush,
    whichever comes first.
    """
    batch: list[dict[str, Any]] = []
    while True:
        try:
            entry = await asyncio.wait_for(_AUDIT_QUEUE.get(), timeout=_FLUSH_INTERVAL)
            if entry is None:
                break
            batch.append(entry)
            if len(batch) >= _BATCH_SIZE:
                await _flush_batch(batch)
                batch.clear()
        except asyncio.TimeoutError:
            if batch:
                await _flush_batch(batch)
                batch.clear()

    # Drain remaining entries on shutdown
    if batch:
        await _flush_batch(batch)


async def enqueue_shutdown_signal() -> None:
    """Signal the flush worker to shut down gracefully."""
    await _AUDIT_QUEUE.put(None)


async def drain_audit_queue() -> None:
    """Force-flush all pending entries (called during shutdown)."""
    remaining: list[dict[str, Any]] = []
    while not _AUDIT_QUEUE.empty():
        entry = _AUDIT_QUEUE.get_nowait()
        if entry is not None:
            remaining.append(entry)
    if remaining:
        await _flush_batch(remaining)


# ---------------------------------------------------------------------------
# Query service (unchanged contract)
# ---------------------------------------------------------------------------


class AuditService:
    async def list_audit_logs(
        self,
        limit: int = 50,
        resource_type: str | None = None,
        status: str | None = None,
    ) -> list[AuditLogSummary]:
        query: Select[tuple[AuditLog]] = (
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        )

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
