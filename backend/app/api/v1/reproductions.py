"""Read and create workspace-owned paper-reproduction tasks."""

from datetime import datetime
import json
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.api.dependencies import get_database_session
from app.auth import DemoIdentity, get_demo_identity
from app.db.models import ReproductionTask
from app.services.reproduction_catalog import (
    ReproductionKind,
    ReproductionStatus,
    create_reproduction_task,
    get_reproduction_task,
    list_reproduction_tasks,
)


router = APIRouter(prefix="/api/v1/reproductions", tags=["reproductions"])


class ReproductionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    kind: ReproductionKind
    source: str = Field(default="", max_length=20_000)
    claim: str = Field(default="", max_length=20_000)
    baseline: dict[str, Any] | None = None
    criteria_version: str | None = Field(default=None, max_length=64)
    linked_project_id: UUID | None = None
    workspace_id: UUID | None = None

    @model_validator(mode="after")
    def bound_baseline_size(self) -> "ReproductionCreate":
        """Keep baseline metadata bounded before it is persisted as JSON."""
        if self.baseline is not None and len(
            json.dumps(self.baseline, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ) > 64_000:
            raise ValueError("baseline metadata exceeds the 64 KB limit")
        return self


class ReproductionTaskRead(BaseModel):
    id: UUID
    workspace_id: UUID
    linked_project_id: UUID | None
    title: str
    kind: Literal["paper", "experiment"]
    source: str
    claim: str
    baseline: dict[str, Any] | None
    criteria_version: str | None
    status: ReproductionStatus
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_task(cls, task: ReproductionTask) -> "ReproductionTaskRead":
        """Expose the task record without deriving scientific conclusions."""
        return cls(
            id=task.id,
            workspace_id=task.workspace_id,
            linked_project_id=task.linked_project_id,
            title=task.title,
            kind=task.kind,
            source=task.source,
            claim=task.claim,
            baseline=task.baseline,
            criteria_version=task.criteria_version,
            status=task.status,
            created_by=task.created_by,
            updated_by=task.updated_by,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


@router.get("", response_model=list[ReproductionTaskRead])
def read_reproduction_tasks(
    kind: ReproductionKind | None = None,
    task_status: ReproductionStatus | None = Query(default=None, alias="status"),
    linked_project_id: UUID | None = None,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> list[ReproductionTaskRead]:
    """List the authenticated user's workspace-visible tasks."""
    tasks = list_reproduction_tasks(
        session,
        identity,
        kind=kind,
        status=task_status,
        linked_project_id=linked_project_id,
    )
    return [ReproductionTaskRead.from_task(task) for task in tasks]


@router.post("", response_model=ReproductionTaskRead, status_code=status.HTTP_201_CREATED)
def create_reproduction_task_route(
    payload: ReproductionCreate,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> ReproductionTaskRead:
    task = create_reproduction_task(
        session,
        identity,
        title=payload.title,
        kind=payload.kind,
        source=payload.source,
        claim=payload.claim,
        baseline=payload.baseline,
        criteria_version=payload.criteria_version,
        linked_project_id=payload.linked_project_id,
        workspace_id=payload.workspace_id,
    )
    return ReproductionTaskRead.from_task(task)


@router.get("/{task_id}", response_model=ReproductionTaskRead)
def read_reproduction_task(
    task_id: UUID,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> ReproductionTaskRead:
    task = get_reproduction_task(session, identity, task_id)
    return ReproductionTaskRead.from_task(task)
