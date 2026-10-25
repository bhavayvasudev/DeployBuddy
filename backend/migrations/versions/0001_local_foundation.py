"""Create the independent, empty Deploy Buddy schema."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_local_foundation"
down_revision = None
branch_labels = None
depends_on = None


def status_type(name="run_status"):
    # Frozen revision: never import mutable application models here.
    return sa.Enum(
        "queued",
        "planned",
        "submitting",
        "provisioning",
        "succeeded",
        "failed",
        "timed_out",
        "ambiguous",
        native_enum=False,
        create_constraint=True,
        name=name,
    )


def upgrade() -> None:
    op.create_table(
        "deployment_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.Uuid(), nullable=False),
        sa.Column("repository_url", sa.String(512), nullable=False),
        sa.Column("service_name", sa.String(63), nullable=False),
        sa.Column("build_command", sa.String(1024), nullable=False),
        sa.Column("start_command", sa.String(1024), nullable=False),
        sa.Column("provider", sa.String(20), server_default="render", nullable=False),
        sa.Column("mode", sa.String(10), server_default="dry_run", nullable=False),
        sa.Column("status", status_type(), server_default="queued", nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("deadline_at", sa.DateTime(timezone=True)),
        sa.Column("submission_started_at", sa.DateTime(timezone=True)),
        sa.Column("provider_service_id", sa.String(128)),
        sa.Column("provider_deployment_id", sa.String(128)),
        sa.Column("deployed_url", sa.String(2048)),
        sa.CheckConstraint("mode IN ('dry_run', 'live')", name="mode"),
        sa.CheckConstraint("provider = 'render'", name="provider"),
        sa.CheckConstraint("attempt_count >= 0", name="attempt_count"),
        sa.CheckConstraint(
            "(lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL)",
            name="complete_lease",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_deployment_runs_claim", "deployment_runs", ["status", "lease_expires_at", "created_at"]
    )
    op.create_table(
        "status_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", status_type("from_status")),
        sa.Column("to_status", status_type("to_status"), nullable=False),
        sa.Column("message", sa.String(2048), nullable=False),
        sa.Column(
            "details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["run_id"], ["deployment_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_status_events_run_id", "status_events", ["run_id"])
    op.create_table(
        "log_records",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("level IN ('info', 'warning', 'error')", name="level"),
        sa.ForeignKeyConstraint(["run_id"], ["deployment_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_log_records_run_id", "log_records", ["run_id"])


def downgrade() -> None:
    raise RuntimeError("Destructive migrations are disabled in the local foundation.")
