import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from deploy_buddy.api.schemas import ConfirmedRequest, PlanPreview, RequestStatus, ServiceSettings
from deploy_buddy.db.session import request_session
from deploy_buddy.services.planning import preview_plan
from deploy_buddy.services.requests import RequestConflict, load_status, submit_request

router = APIRouter(prefix="/requests", tags=["dry-run requests"])
DatabaseSession = Annotated[Callable[[], AbstractContextManager[Session]], Depends(request_session)]


@router.post("/preview", response_model=PlanPreview)
def preview(settings: ServiceSettings):
    return preview_plan(settings)


@router.post("", response_model=RequestStatus, status_code=201)
def submit(request: ConfirmedRequest, response: Response, session: DatabaseSession):
    try:
        with session() as connection:
            result, created = submit_request(connection, request)
    except RequestConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from None
    response.status_code = 201 if created else 200
    response.headers["Location"] = f"/requests/{result.id}"
    return result


@router.get("/{request_id}", response_model=RequestStatus)
def status(request_id: uuid.UUID, session: DatabaseSession):
    with session() as connection:
        result = load_status(connection, request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Dry-run request not found.")
    return result
