from collections.abc import Sequence
from importlib import import_module
from typing import Protocol, cast

import sqlalchemy as sa


class AlembicOperations(Protocol):
    def create_table(self, *args: object, **kwargs: object) -> object: ...

    def drop_table(self, table_name: str) -> None: ...


op_module = cast(object, import_module("alembic.op"))
op = cast(AlembicOperations, op_module)

revision: str = "20260509_0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    _ = op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    _ = op.create_table(
        "operation_tasks",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("operation_type", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=100), nullable=False),
        sa.Column("target_id", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.String(length=2000), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    _ = op.create_table(
        "resource_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("resource_name", sa.String(length=255), nullable=True),
        sa.Column("project_id", sa.String(length=255), nullable=True),
        sa.Column("sync_status", sa.String(length=50), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("external_id", name="uq_resource_snapshots_external_id"),
    )


def downgrade() -> None:
    op.drop_table("resource_snapshots")
    op.drop_table("operation_tasks")
    op.drop_table("audit_logs")
