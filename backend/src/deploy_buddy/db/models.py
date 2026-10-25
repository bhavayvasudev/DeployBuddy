import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    metadata = sa.MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class RunStatus(enum.StrEnum):
    QUEUED = "queued"
    PLANNED = "planned"
    SUBMITTING = "submitting"
    PROVISIONING = "provisioning"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    AMBIGUOUS = "ambiguous"


def status_type(name: str = "run_status") -> sa.Enum:
    return sa.Enum(
        RunStatus,
        values_callable=lambda values: [v.value for v in values],
        native_enum=False,
        create_constraint=True,
        name=name,
    )


class DeploymentRun(Base):
    __tablename__ = "deployment_runs"
    __table_args__ = (
        sa.CheckConstraint("mode IN ('dry_run', 'live')", name="mode"),
        sa.CheckConstraint("provider = 'render'", name="provider"),
        sa.CheckConstraint("attempt_count >= 0", name="attempt_count"),
        sa.CheckConstraint(
            "(lease_owner IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL) OR "
            "(lease_owner IS NOT NULL AND lease_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL)",
            name="complete_lease",
        ),
        sa.Index("ix_deployment_runs_claim", "status", "lease_expires_at", "created_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(sa.Uuid, unique=True, nullable=False)
    repository_url: Mapped[str] = mapped_column(sa.String(512))
    service_name: Mapped[str] = mapped_column(sa.String(63))
    build_command: Mapped[str] = mapped_column(sa.String(1024))
    start_command: Mapped[str] = mapped_column(sa.String(1024))
    provider: Mapped[str] = mapped_column(sa.String(20), server_default="render")
    mode: Mapped[str] = mapped_column(sa.String(10), server_default="dry_run")
    status: Mapped[RunStatus] = mapped_column(status_type(), server_default="queued")
    confirmed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    plan_digest: Mapped[str | None] = mapped_column(sa.String(64))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )
    attempt_count: Mapped[int] = mapped_column(server_default="0")
    lease_owner: Mapped[str | None] = mapped_column(sa.String(128))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(sa.Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    submission_started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    provider_service_id: Mapped[str | None] = mapped_column(sa.String(128))
    provider_deployment_id: Mapped[str | None] = mapped_column(sa.String(128))
    deployed_url: Mapped[str | None] = mapped_column(sa.String(2048))


class StatusEvent(Base):
    __tablename__ = "status_events"
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("deployment_runs.id"), index=True)
    from_status: Mapped[RunStatus | None] = mapped_column(status_type("from_status"))
    to_status: Mapped[RunStatus] = mapped_column(status_type("to_status"))
    message: Mapped[str] = mapped_column(sa.String(2048))
    details: Mapped[dict] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class DeploymentOperation(Base):
    __tablename__ = "deployment_operations"
    __table_args__ = (
        sa.UniqueConstraint("run_id", "sequence"),
        sa.CheckConstraint("sequence = 1", name="single_service"),
        sa.CheckConstraint("kind = 'create_node_web_service'", name="kind"),
        sa.CheckConstraint("status = 'planned'", name="status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("deployment_runs.id"), index=True)
    sequence: Mapped[int] = mapped_column()
    kind: Mapped[str] = mapped_column(sa.String(64))
    status: Mapped[str] = mapped_column(sa.String(20), server_default="planned")
    specification: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class LogRecord(Base):
    __tablename__ = "log_records"
    __table_args__ = (sa.CheckConstraint("level IN ('info', 'warning', 'error')", name="level"),)
    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("deployment_runs.id"), index=True)
    level: Mapped[str] = mapped_column(sa.String(10))
    message: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
