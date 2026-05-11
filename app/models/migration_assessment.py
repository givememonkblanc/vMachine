from datetime import datetime
from typing import final
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base.base import Base


@final
class MigrationAssessment(Base):
    __tablename__ = "migration_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    vm_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    vm_name: Mapped[str] = mapped_column(String(255), nullable=False)
    vm_power_state: Mapped[str] = mapped_column(String(50), nullable=True)
    vm_guest_os: Mapped[str | None] = mapped_column(String(255), nullable=True)

    compatible: Mapped[bool] = mapped_column(nullable=False)
    compatibility_score: Mapped[float] = mapped_column(Float, default=0.0)
    compatibility_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    flavor_match: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    network_mappings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    disk_mappings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    mapping_score: Mapped[float] = mapped_column(Float, default=0.0)

    source_vm_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    issues: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    warnings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    assessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plans: Mapped[list["MigrationPlan"]] = relationship(
        "MigrationPlan", back_populates="assessment", cascade="all, delete-orphan"
    )


@final
class MigrationPlan(Base):
    __tablename__ = "migration_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    assessment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("migration_assessments.id", ondelete="CASCADE"), nullable=False
    )
    vm_id: Mapped[str] = mapped_column(String(255), nullable=False)

    priority: Mapped[int] = mapped_column(Integer, default=5)
    target_flavor_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_flavor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_network_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    target_volume_types: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    estimated_downtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    estimated_total_minutes: Mapped[int] = mapped_column(Integer, default=0)
    steps: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="pending")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    assessment: Mapped["MigrationAssessment"] = relationship(
        "MigrationAssessment", back_populates="plans"
    )
