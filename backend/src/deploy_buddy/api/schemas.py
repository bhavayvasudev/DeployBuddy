"""Closed, credential-free input and output contracts for the local dry-run flow."""

import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ServiceSettings(Contract):
    repository_url: str = Field(max_length=512)
    service_name: str = Field(pattern=r"^[a-z][a-z0-9-]{0,61}[a-z0-9]$|^[a-z]$", max_length=63)
    build_command: Literal["npm ci", "npm ci && npm run build"] = "npm ci && npm run build"
    start_command: Literal["npm start"] = "npm start"
    runtime: Literal["node"] = "node"
    service_type: Literal["web"] = "web"
    provider: Literal["render"] = "render"
    mode: Literal["dry_run"] = "dry_run"

    @field_validator("repository_url")
    @classmethod
    def public_github_url(cls, value: str) -> str:
        # Deliberately do not parse arbitrary URLs or follow redirects. No credentials,
        # ports, escapes, query strings, fragments, subpaths, SSH or alternate hosts.
        match = re.fullmatch(
            r"https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/"
            r"([A-Za-z0-9_.-]{1,100})/?",
            value,
        )
        if not match:
            raise ValueError("Use a public GitHub HTTPS repository URL.")
        owner, repository = match.groups()
        if "--" in owner:
            raise ValueError("Invalid GitHub owner.")
        if repository.endswith(".git"):
            repository = repository[:-4]
        if repository in {"", ".", ".."}:
            raise ValueError("Invalid GitHub repository.")
        return f"https://github.com/{owner.lower()}/{repository.lower()}"


class PlannedOperation(Contract):
    sequence: Literal[1] = 1
    kind: Literal["create_node_web_service"] = "create_node_web_service"
    description: str = "Plan one Node.js web service on Render; do not execute it."
    settings: ServiceSettings


class PlanPreview(Contract):
    plan_digest: str
    settings: ServiceSettings
    operations: list[PlannedOperation]
    notice: str


class ConfirmedRequest(ServiceSettings):
    # UUID conversion is explicitly limited to this field; booleans remain strict.
    idempotency_key: uuid.UUID = Field(strict=False)
    confirmed: Literal[True]
    plan_digest: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_boolean_confirmation(cls, value):
        if value is not True:
            raise ValueError("Explicit confirmation is required.")
        return value


class AuditEvent(Contract):
    id: int
    from_status: str | None
    to_status: str
    message: str
    created_at: datetime


class RequestStatus(Contract):
    id: uuid.UUID
    mode: Literal["dry_run"] = "dry_run"
    status: Literal["planned"] = "planned"
    confirmed_at: datetime
    created_at: datetime
    plan_digest: str
    operations: list[PlannedOperation]
    events: list[AuditEvent]
