from __future__ import annotations

import uuid
from datetime import datetime
from typing import final

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base.base import Base


class TaskState:
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

    _VALID_TRANSITIONS: dict[str, set[str]] = {
        QUEUED: {RUNNING, CANCELLED},
        RUNNING: {SUCCEEDED, FAILED, TIMEOUT},
        SUCCEEDED: set(),
        FAILED: {QUEUED},  # retry
        TIMEOUT: {QUEUED},  # retry
        CANCELLED: set(),
    }

    @classmethod
    def can_transition(cls, current: str, target: str) -> bool:
        return target in cls._VALID_TRANSITIONS.get(current, set())

    @classmethod
    def terminal(cls) -> set[str]:
        return {cls.SUCCEEDED, cls.FAILED, cls.TIMEOUT, cls.CANCELLED}


@final
class OperationTask(Base):
    __tablename__ = "operation_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    operation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # State machine
    state: Mapped[str] = mapped_column(String(50), nullable=False, default=TaskState.QUEUED)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Task-specific payload (replaces MigrationTask-specific columns)
    extra: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    # History of retries and errors (list of dicts)
    events: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)

    def transition_to(self, new_state: str) -> None:
        """Transition the task state with validation."""
        if not TaskState.can_transition(self.state, new_state):
            allowed = TaskState._VALID_TRANSITIONS.get(self.state, set())
            raise ValueError(
                f"Invalid transition: {self.state} → {new_state} "
                f"(allowed: {allowed})"
            )
        self.state = new_state
        if new_state in TaskState.terminal():
            self.finished_at = datetime.now()
