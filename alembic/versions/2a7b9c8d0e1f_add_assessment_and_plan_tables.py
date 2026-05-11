"""add migration assessment and plan tables

Revision ID: 2a7b9c8d0e1f
Revises: 6f4e3554a006
Create Date: 2026-05-11 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2a7b9c8d0e1f"
down_revision: Union[str, Sequence[str], None] = "6f4e3554a006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "migration_assessments",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("vm_id", sa.String(255), nullable=False),
        sa.Column("vm_name", sa.String(255), nullable=False),
        sa.Column("vm_power_state", sa.String(50), nullable=True),
        sa.Column("vm_guest_os", sa.String(255), nullable=True),
        sa.Column("compatible", sa.Boolean(), nullable=False),
        sa.Column("compatibility_score", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("compatibility_detail", sa.JSON(), nullable=True),
        sa.Column("flavor_match", sa.JSON(), nullable=True),
        sa.Column("network_mappings", sa.JSON(), nullable=True),
        sa.Column("disk_mappings", sa.JSON(), nullable=True),
        sa.Column("mapping_score", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("source_vm_metadata", sa.JSON(), nullable=True),
        sa.Column("issues", sa.JSON(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=True),
        sa.Column(
            "assessed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_migration_assessments_vm_id"), "migration_assessments", ["vm_id"], unique=False)

    op.create_table(
        "migration_plans",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("assessment_id", sa.String(36), nullable=False),
        sa.Column("vm_id", sa.String(255), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("target_flavor_id", sa.String(255), nullable=True),
        sa.Column("target_flavor_name", sa.String(255), nullable=True),
        sa.Column("target_network_ids", sa.JSON(), nullable=True),
        sa.Column("target_volume_types", sa.JSON(), nullable=True),
        sa.Column("estimated_downtime_minutes", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("estimated_total_minutes", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("steps", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["migration_assessments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("migration_plans")
    op.drop_index(op.f("ix_migration_assessments_vm_id"), table_name="migration_assessments")
    op.drop_table("migration_assessments")
