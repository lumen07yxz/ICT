"""Fixed, pending-only proposal creation and membership-scoped proposal reading."""

from datetime import datetime, timezone
import hmac
import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_database_session
from app.auth import DemoIdentity, get_demo_identity
from app.db.models import RunProposal
from app.errors import AppError
from app.services.run_proposals import (
    DEMO_DATASET_VERSION,
    DEMO_PIPELINE_TEMPLATE,
    DEMO_PROJECT_KEY,
    create_run_proposal,
    list_visible_run_proposals,
)


router = APIRouter(tags=["run-proposals"])
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class RunProposalCreate(BaseModel):
    """Request accepted only from the MCP service, with a fixed synthetic schema."""

    model_config = ConfigDict(extra="forbid", strict=True)

    project_id: Literal["demo-research"]
    dataset_version: Literal["dataset-synthetic-v1"]
    pipeline_template: Literal["research-smoke-v1"]
    sample_limit: int = Field(ge=1, le=100)


class RunProposalRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    project_id: UUID
    dataset_version: str
    pipeline_template: str
    parameters: dict[str, int]
    config_sha256: str
    trace_id: str
    status: str
    approved_by: str | None
    approved_at: datetime | None
    run_id: UUID | None
    created_at: datetime
    expires_at: datetime


def _require_internal_mcp_key(
    request: Request,
    supplied_key: str | None = Header(default=None, alias="X-ICT-Internal-Key"),
) -> None:
    """Authenticate the private MCP-to-API hop with a server-only credential."""
    expected_key = request.app.state.internal_api_key
    if not expected_key:
        raise AppError(503, "INTERNAL_AUTH_NOT_CONFIGURED")
    if not supplied_key or not hmac.compare_digest(
        supplied_key.encode("utf-8"), expected_key.encode("utf-8")
    ):
        raise AppError(401, "INTERNAL_UNAUTHORIZED")


def _response_status(proposal: RunProposal, *, now: datetime | None = None) -> str:
    """Expose an expired label without mutating the pending proposal during a read."""
    if proposal.status != "pending_approval":
        return proposal.status
    current = now or datetime.now(timezone.utc)
    expiry = proposal.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return "expired" if expiry <= current else "pending_approval"


def _proposal_read(proposal: RunProposal, status_value: str | None = None) -> RunProposalRead:
    return RunProposalRead(
        id=proposal.id,
        project_id=proposal.project_id,
        dataset_version=DEMO_DATASET_VERSION,
        pipeline_template=proposal.pipeline_template,
        parameters=proposal.parameters,
        config_sha256=proposal.config_sha256,
        trace_id=proposal.trace_id,
        status=status_value or _response_status(proposal),
        approved_by=proposal.approved_by,
        approved_at=proposal.approved_at,
        run_id=proposal.run.id if proposal.run is not None else None,
        created_at=proposal.created_at,
        expires_at=proposal.expires_at,
    )


@router.post(
    "/internal/v1/run-proposals",
    response_model=RunProposalRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def create_internal_run_proposal(
    payload: RunProposalCreate,
    response: Response,
    _internal_key: None = Depends(_require_internal_mcp_key),
    session: Session = Depends(get_database_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RunProposalRead:
    """Insert an inert proposal; this endpoint has no run or worker side effect."""
    if not idempotency_key or not IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key):
        raise AppError(422, "INVALID_IDEMPOTENCY_KEY")
    if (
        payload.project_id != DEMO_PROJECT_KEY
        or payload.dataset_version != DEMO_DATASET_VERSION
        or payload.pipeline_template != DEMO_PIPELINE_TEMPLATE
    ):
        raise AppError(422, "INVALID_REQUEST")

    proposal, created = create_run_proposal(
        session,
        idempotency_key=idempotency_key,
        sample_limit=payload.sample_limit,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return _proposal_read(proposal)


@router.get("/api/v1/run-proposals", response_model=list[RunProposalRead])
def read_run_proposals(
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> list[RunProposalRead]:
    """Read only proposals inside the caller's explicit project memberships."""
    return [
        _proposal_read(proposal)
        for proposal in list_visible_run_proposals(session, identity.user_id)
    ]
