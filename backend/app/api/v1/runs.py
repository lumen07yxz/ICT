"""Operator approval and membership-scoped status reads for synthetic runs."""

from datetime import datetime, timezone
import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.dependencies import get_database_session
from app.api.v1.run_proposals import _require_internal_mcp_key
from app.auth import DemoIdentity, get_demo_identity
from app.db.models import Run, RunEvent
from app.errors import AppError
from app.services.run_proposals import DEMO_DATASET_VERSION
from app.services.runs import (
    approve_run_proposal,
    get_visible_run,
    list_visible_runs,
    list_visible_run_events,
    mark_run_dispatch_failed,
)


logger = logging.getLogger("ict.api")


router = APIRouter(tags=["runs"])
RunState = Literal["queued", "running", "succeeded", "failed"]


class RunRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    proposal_id: UUID
    project_id: UUID
    dataset_version: Literal["dataset-synthetic-v1"]
    pipeline_template: Literal["research-smoke-v1"]
    parameters: dict[str, int]
    config_sha256: str
    quality_status: Literal["success", "warning"] | None
    quality_rule_set_version: str | None
    quality_report_sha256: str | None
    trace_id: str
    status: RunState
    result: dict[str, object] | None
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class RunEventRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: Literal[1, 2, 3]
    status: RunState
    error_code: Literal["QUEUE_UNAVAILABLE", "WORKER_EXECUTION_FAILED"] | None
    occurred_at: datetime


def _run_read(run: Run) -> RunRead:
    return RunRead(
        id=run.id,
        proposal_id=run.proposal_id,
        project_id=run.project_id,
        dataset_version=DEMO_DATASET_VERSION,
        pipeline_template=run.pipeline_template,
        parameters=run.parameters,
        config_sha256=run.config_sha256,
        quality_status=run.quality_status,
        quality_rule_set_version=run.quality_rule_set_version,
        quality_report_sha256=run.quality_report_sha256,
        trace_id=run.trace_id,
        status=run.status,
        result=run.result,
        error_code=run.error_code,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _run_event_read(event: RunEvent) -> RunEventRead:
    occurred_at = event.occurred_at
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    else:
        occurred_at = occurred_at.astimezone(timezone.utc)
    return RunEventRead(
        sequence=event.sequence,
        status=event.status,
        error_code=event.error_code,
        occurred_at=occurred_at,
    )


@router.post(
    "/api/v1/run-proposals/{proposal_id}/approve",
    response_model=RunRead,
    status_code=status.HTTP_201_CREATED,
)
def approve_proposal_route(
    proposal_id: UUID,
    request: Request,
    response: Response,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> RunRead:
    """Require a project operator, then enqueue only after the approval transaction commits."""
    if identity.role != "operator":
        raise AppError(403, "FORBIDDEN")
    run, created = approve_run_proposal(session, identity, proposal_id)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    if created:
        try:
            request.app.state.run_dispatcher(run.id)
        except Exception as exc:
            # The committed run remains visible; queue failure becomes an explicit terminal state.
            failed = mark_run_dispatch_failed(session, run.id)
            if failed is not None:
                run = failed
            request_id = getattr(request.state, "request_id", "")
            logger.error(
                "run_dispatch_failed request_id=%s run_id=%s trace_id=%s error_code=QUEUE_UNAVAILABLE error_type=%s",
                request_id,
                run.id,
                run.trace_id,
                type(exc).__name__,
            )
    return _run_read(run)


@router.get("/api/v1/runs", response_model=list[RunRead])
def read_runs(
    project_id: UUID | None = None,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> list[RunRead]:
    """List member-visible runs, optionally narrowed to one authorized project."""
    return [_run_read(run) for run in list_visible_runs(session, identity.user_id, project_id)]


@router.get("/api/v1/runs/{run_id}", response_model=RunRead)
def read_run(
    run_id: UUID,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> RunRead:
    """Read one run only inside the caller's project membership boundary."""
    return _run_read(get_visible_run(session, identity.user_id, run_id))


@router.get("/api/v1/runs/{run_id}/events", response_model=list[RunEventRead])
def read_run_events(
    run_id: UUID,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> list[RunEventRead]:
    """Return only the fixed event fields for a member-visible run."""
    return [
        _run_event_read(event)
        for event in list_visible_run_events(session, identity.user_id, run_id)
    ]


@router.get(
    "/internal/v1/runs/{run_id}",
    response_model=RunRead,
    include_in_schema=False,
)
def read_internal_run_status(
    run_id: UUID,
    _internal_key: None = Depends(_require_internal_mcp_key),
    session: Session = Depends(get_database_session),
) -> RunRead:
    """Expose a fixed synthetic run DTO only to the authenticated MCP service."""
    run = session.get(Run, run_id)
    if run is None or run.pipeline_template != "research-smoke-v1":
        raise AppError(404, "RUN_NOT_FOUND")
    return _run_read(run)
