import uuid
from datetime import datetime
from typing import final

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base.base import Base


@final
class AutoScalingPolicy(Base):
    __tablename__ = "auto_scaling_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    threshold: Mapped[float] = mapped_column(nullable=False)
    comparison: Mapped[str] = mapped_column(String(20), nullable=False, default="gt")
    min_replicas: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_replicas: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    target_resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    extra: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
