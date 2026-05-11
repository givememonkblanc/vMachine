import uuid as _uuid
from datetime import datetime, timezone
from typing import cast

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SASession

from app.core.config.settings import get_settings
from app.db.base import Base
from app.models.audit_log import AuditLog
from app.models.operation_task import OperationTask
from tests.conftest import create_test_client


def _sync_engine():
    settings = get_settings()
    sync_url = settings.database_url.replace("+aiosqlite", "+pysqlite")
    engine = create_engine(sync_url)
    Base.metadata.create_all(bind=engine)
    return engine


def insert_audit_log() -> str:
    uid = _uuid.uuid4()
    engine = _sync_engine()
    with SASession(engine) as session:
        entry = AuditLog(
            id=uid,
            actor=None,
            action="test_audit",
            resource_type="test",
            resource_id="audit-1",
            status="success",
        )
        session.add(entry)
        session.commit()
    engine.dispose()
    return str(uid)


def insert_operation_task(operation_type: str, target_id: str) -> str:
    uid = _uuid.uuid4()
    engine = _sync_engine()
    with SASession(engine) as session:
        task = OperationTask(
            id=uid,
            operation_type=operation_type,
            target_type="test",
            target_id=target_id,
            state="queued",
        )
        session.add(task)
        session.commit()
    engine.dispose()
    return str(uid)


def test_audit_logs_endpoint_returns_created_entry() -> None:
    entry_id = insert_audit_log()

    client = create_test_client()
    response = client.get("/api/v1/audit/logs?resource_type=test")

    assert response.status_code == 200
    body = cast(dict[str, list[dict[str, object]]], response.json())
    items = body["items"]
    assert any(item["id"] == entry_id for item in items)


def test_operation_tasks_endpoint_returns_created_task() -> None:
    task_id = insert_operation_task("test_operation", "task-1")

    client = create_test_client()
    response = client.get("/api/v1/operations/tasks?target_type=test")

    assert response.status_code == 200
    body = cast(dict[str, list[dict[str, object]]], response.json())
    items = body["items"]
    assert any(item["id"] == task_id for item in items)


def test_operation_task_detail_endpoint_returns_task() -> None:
    task_id = insert_operation_task("detail_operation", "task-2")

    client = create_test_client()
    response = client.get(f"/api/v1/operations/tasks/{task_id}")

    assert response.status_code == 200
    body = cast(dict[str, object], response.json())
    assert body["id"] == task_id
    assert body["operation_type"] == "detail_operation"
