"""Persist the confirmed proposal and its single planned operation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_dry_run_requests"
down_revision = "0001_local_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deployment_runs", sa.Column("plan_digest", sa.String(64), nullable=True))
    op.create_table(
        "deployment_operations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), server_default="planned", nullable=False),
        sa.Column("specification", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["deployment_runs.id"]),
        sa.UniqueConstraint("run_id", "sequence"),
        sa.CheckConstraint("sequence = 1", name="single_service"),
        sa.CheckConstraint("kind = 'create_node_web_service'", name="kind"),
        sa.CheckConstraint("status = 'planned'", name="status"),
    )
    op.create_index("ix_deployment_operations_run_id", "deployment_operations", ["run_id"])


def downgrade() -> None:
    raise RuntimeError("Destructive migrations are disabled.")
