import uuid
from datetime import datetime
from typing import final

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base.base import Base


@final
class MigrationTask(Base):
    __tablename__ = "migration_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    migration_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    destination_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, default="server")
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
