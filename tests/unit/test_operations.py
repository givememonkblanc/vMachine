from datetime import datetime, timezone
import sqlite3
from typing import cast
from uuid import uuid4

from tests.conftest import create_test_client


def insert_audit_log() -> str:
    entry_id = str(uuid4())
    connection = sqlite3.connect("okastro.db")
    try:
        _ = connection.execute(
            "insert into audit_logs (id, actor, action, resource_type, resource_id, status, request_id, payload, created_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry_id,
                None,
                "test_audit",
                "test",
                "audit-1",
                "success",
                None,
                None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return entry_id


def insert_operation_task(operation_type: str, target_id: str) -> str:
    task_id = str(uuid4())
    connection = sqlite3.connect("okastro.db")
    try:
        _ = connection.execute(
            "insert into operation_tasks (id, operation_type, target_type, target_id, state, error_message, submitted_at, finished_at) values (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task_id,
                operation_type,
                "test",
                target_id,
                "queued",
                None,
                datetime.now(timezone.utc).isoformat(),
                None,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return task_id


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
