import hmac
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from deploy_buddy.api.schemas import (
    AuditEvent,
    ConfirmedRequest,
    PlannedOperation,
    RequestStatus,
    ServiceSettings,
)
from deploy_buddy.db.models import DeploymentOperation, DeploymentRun, RunStatus, StatusEvent
from deploy_buddy.services.planning import preview_plan


class RequestConflict(ValueError):
    pass


def load_status(session: Session, run_id: uuid.UUID) -> RequestStatus | None:
    run = session.get(DeploymentRun, run_id)
    if run is None or run.mode != "dry_run" or run.plan_digest is None:
        return None
    operations = session.scalars(
        select(DeploymentOperation)
        .where(DeploymentOperation.run_id == run_id)
        .order_by(DeploymentOperation.sequence)
    ).all()
    events = session.scalars(
        select(StatusEvent).where(StatusEvent.run_id == run_id).order_by(StatusEvent.id)
    ).all()
    return RequestStatus(
        id=run.id,
        status=run.status.value,
        confirmed_at=run.confirmed_at,
        created_at=run.created_at,
        plan_digest=run.plan_digest,
        operations=[PlannedOperation.model_validate(row.specification) for row in operations],
        events=[
            AuditEvent(
                id=event.id,
                from_status=event.from_status.value if event.from_status else None,
                to_status=event.to_status.value,
                message=event.message,
                created_at=event.created_at,
            )
            for event in events
        ],
    )


def submit_request(session: Session, request: ConfirmedRequest) -> tuple[RequestStatus, bool]:
    # Revalidate even callers outside HTTP. No generic dict or mode override can bypass this.
    request = ConfirmedRequest.model_validate(request.model_dump())
    settings = ServiceSettings.model_validate(
        request.model_dump(include=set(ServiceSettings.model_fields))
    )
    plan = preview_plan(settings)
    if not hmac.compare_digest(request.plan_digest, plan.plan_digest):
        raise RequestConflict("The proposal changed. Preview it again before confirming.")
    with session.begin():
        # PostgreSQL arbitrates concurrent duplicates; no check-then-insert race.
        run_id = session.scalar(
            insert(DeploymentRun)
            .values(
                id=uuid.uuid4(),
                idempotency_key=request.idempotency_key,
                repository_url=settings.repository_url,
                service_name=settings.service_name,
                build_command=settings.build_command,
                start_command=settings.start_command,
                mode="dry_run",
                provider="render",
                status=RunStatus.PLANNED,
                confirmed_at=datetime.now(UTC),
                plan_digest=plan.plan_digest,
            )
            .on_conflict_do_nothing(index_elements=[DeploymentRun.idempotency_key])
            .returning(DeploymentRun.id)
        )
        created = run_id is not None
        if not created:
            existing = session.scalar(
                select(DeploymentRun).where(
                    DeploymentRun.idempotency_key == request.idempotency_key
                )
            )
            if existing.mode != "dry_run" or existing.plan_digest != plan.plan_digest:
                raise RequestConflict("Idempotency key already used for a different request.")
            run_id = existing.id
        else:
            session.add(
                DeploymentOperation(
                    run_id=run_id,
                    sequence=1,
                    kind=plan.operations[0].kind,
                    specification=plan.operations[0].model_dump(),
                )
            )
            session.add_all(
                [
                    StatusEvent(
                        run_id=run_id,
                        from_status=None,
                        to_status=RunStatus.QUEUED,
                        message="Explicitly confirmed dry-run request accepted locally.",
                        details={"plan_digest": plan.plan_digest, "confirmed": True},
                    ),
                    StatusEvent(
                        run_id=run_id,
                        from_status=RunStatus.QUEUED,
                        to_status=RunStatus.PLANNED,
                        message="One operation planned. External execution is disabled.",
                        details={"operation_count": 1, "external_calls": 0},
                    ),
                ]
            )
            session.flush()
        result = load_status(session, run_id)
    # Only return after commit succeeds. All writes above share one transaction.
    return result, created
