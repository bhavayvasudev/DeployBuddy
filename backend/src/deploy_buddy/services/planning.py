import hashlib
import json

from deploy_buddy.api.schemas import PlannedOperation, PlanPreview, ServiceSettings

NOTICE = (
    "Dry-run only: save a local plan, execute no commands, contact no external services, "
    "and create no external resources. GitHub URL syntax is validated; repository existence, "
    "public visibility and Node.js contents are not verified offline."
)


def preview_plan(settings: ServiceSettings) -> PlanPreview:
    operation = PlannedOperation(settings=settings)
    # Version and the entire user-visible proposal participate in confirmation.
    proposal = {"version": 1, "operations": [operation.model_dump()], "notice": NOTICE}
    digest = hashlib.sha256(
        json.dumps(proposal, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return PlanPreview(settings=settings, operations=[operation], plan_digest=digest, notice=NOTICE)
