from datetime import datetime
from typing import final
from uuid import uuid4

from sqlalchemy import DateTime, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base.base import Base


@final
class ClusterDeployment(Base):
    __tablename__ = "cluster_deployments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cluster_type: Mapped[str] = mapped_column(String(50), nullable=False, default="compute")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    node_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_config: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
