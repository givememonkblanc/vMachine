from datetime import datetime
from typing import final
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base.base import Base


@final
class MetricRecord(Base):
    __tablename__ = "metric_records"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    labels: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    project_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
