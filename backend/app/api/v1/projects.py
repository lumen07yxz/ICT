"""Project and dataset overview API for the fixed demo roles."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session

from app.api.dependencies import get_database_session
from app.auth import DemoIdentity, get_demo_identity
from app.db.models import DatasetVersion, Project, Run, RunProposal, Workflow
from app.db.seed_demo import DEMO_PROJECT_ID
from app.errors import AppError
from app.services.dataset_quality import (
    DatasetQualityReport,
    DEMO_DATASET_VERSION,
    inspect_dataset_manifest,
)
from app.services.project_catalog import create_project, get_project, list_projects
from app.services.template_registry import (
    DEMO_PIPELINE_TEMPLATE,
    TemplateFieldContract,
    TemplateRegistryError,
    TemplateResourceLimits,
    load_template_manifest,
)


router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    domain: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=4000)


class ProjectListItem(BaseModel):
    id: UUID
    name: str
    domain: str
    description: str
    role: str
    visibility: Literal["private", "demo"]
    created_at: datetime
    workflow_count: int
    dataset_version_count: int
    recent_run_status: Literal["queued", "running", "succeeded", "failed"] | None
    last_activity_at: datetime | None


class DatasetVersionRead(BaseModel):
    id: UUID
    version: str
    source: str
    license_status: str
    manifest_ref: str
    schema_ref: str
    research_ready: bool


class ProjectRead(BaseModel):
    id: UUID
    name: str
    domain: str
    description: str
    role: str
    visibility: Literal["private", "demo"]
    created_at: datetime
    datasets: list[DatasetVersionRead]
    pipeline_templates: list[str]


class PipelineTemplateRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str
    version: str
    manifest_sha256: str
    executor: Literal["synthetic_smoke_v1"]
    dataset_version: str
    permission_scope: Literal["synthetic_dataset_manifest_read_only"]
    resource_limits: TemplateResourceLimits
    inputs: dict[str, TemplateFieldContract]
    parameters: dict[str, TemplateFieldContract]
    outputs: dict[str, TemplateFieldContract]
    states: list[Literal["queued", "running", "succeeded", "failed"]]
    error_codes: list[
        Literal[
            "DATA_QUALITY_BLOCKED",
            "PROPOSAL_CONFIG_MISMATCH",
            "QUEUE_UNAVAILABLE",
            "WORKER_EXECUTION_FAILED",
        ]
    ]


class QualityIssueRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: Literal["blocker", "warning"]
    message: str
    count: int
    line_numbers: list[int]
    guidance: str


class DatasetQualityReportRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_version: str
    status: Literal["blocker", "warning", "success"]
    rule_set_version: str
    manifest_sha256: str
    row_count: int
    split_counts: dict[str, int]
    label_category_count: int
    issues: list[QualityIssueRead]
    synthetic_only: bool
    research_ready: bool
    checked_at: datetime


def _quality_report_read(report: DatasetQualityReport) -> DatasetQualityReportRead:
    """Expose only aggregate counts, safe issue details, and the manifest digest."""
    return DatasetQualityReportRead(
        dataset_version=report.dataset_version,
        status=report.status,
        rule_set_version=report.rule_set_version,
        manifest_sha256=report.manifest_sha256,
        row_count=report.row_count,
        split_counts=dict(report.split_counts),
        label_category_count=report.label_category_count,
        issues=[
            QualityIssueRead(
                code=issue.code,
                severity=issue.severity,
                message=issue.message,
                count=issue.count,
                line_numbers=list(issue.line_numbers),
                guidance=issue.guidance,
            )
            for issue in report.issues
        ],
        synthetic_only=report.synthetic_only,
        research_ready=report.research_ready,
        checked_at=report.checked_at,
    )


def _project_read(project: Project, role: str) -> ProjectRead:
    datasets = [
        DatasetVersionRead(
            id=dataset.id,
            version=dataset.version,
            source=dataset.source,
            license_status=dataset.license_status,
            manifest_ref=dataset.manifest_ref,
            schema_ref=dataset.schema_ref,
            research_ready=False,
        )
        for dataset in project.dataset_versions
    ]
    return ProjectRead(
        id=project.id,
        name=project.name,
        domain=project.domain,
        description=project.description,
        role=role,
        visibility=project.visibility,
        created_at=project.created_at,
        datasets=datasets,
        pipeline_templates=["research-smoke-v1"] if project.visibility == "demo" else [],
    )


@router.get("", response_model=list[ProjectListItem])
def read_projects(
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> list[ProjectListItem]:
    """List projects visible to the authenticated demo user."""
    visible_projects = list_projects(session, identity)
    project_ids = [project.id for project, _role in visible_projects]
    if not project_ids:
        return []

    # Aggregate only projects already scoped by the caller's membership.
    workflow_counts = dict(session.execute(
        select(Workflow.project_id, func.count(Workflow.id))
        .where(Workflow.project_id.in_(project_ids))
        .group_by(Workflow.project_id)
    ).all())
    dataset_counts = dict(session.execute(
        select(DatasetVersion.project_id, func.count(DatasetVersion.id))
        .where(DatasetVersion.project_id.in_(project_ids))
        .group_by(DatasetVersion.project_id)
    ).all())

    activity_rows = union_all(
        select(Project.id.label("project_id"), Project.created_at.label("activity_at"))
        .where(Project.id.in_(project_ids)),
        select(DatasetVersion.project_id, DatasetVersion.created_at)
        .where(DatasetVersion.project_id.in_(project_ids)),
        select(Workflow.project_id, Workflow.updated_at)
        .where(Workflow.project_id.in_(project_ids)),
        select(RunProposal.project_id, RunProposal.created_at)
        .where(RunProposal.project_id.in_(project_ids)),
        select(Run.project_id, func.coalesce(Run.finished_at, Run.started_at, Run.created_at))
        .where(Run.project_id.in_(project_ids)),
    ).subquery("project_activity")
    last_activity = dict(session.execute(
        select(activity_rows.c.project_id, func.max(activity_rows.c.activity_at))
        .group_by(activity_rows.c.project_id)
    ).all())

    latest_runs = select(
        Run.project_id.label("project_id"),
        Run.status.label("status"),
        func.row_number().over(
            partition_by=Run.project_id,
            order_by=(Run.created_at.desc(), Run.id.desc()),
        ).label("position"),
    ).where(Run.project_id.in_(project_ids)).subquery("ranked_project_runs")
    recent_run_status = dict(session.execute(
        select(latest_runs.c.project_id, latest_runs.c.status)
        .where(latest_runs.c.position == 1)
    ).all())

    return [
        ProjectListItem(
            id=project.id,
            name=project.name,
            domain=project.domain,
            description=project.description,
            role=role,
            visibility=project.visibility,
            created_at=project.created_at,
            workflow_count=workflow_counts.get(project.id, 0),
            dataset_version_count=dataset_counts.get(project.id, 0),
            recent_run_status=recent_run_status.get(project.id),
            last_activity_at=last_activity.get(project.id),
        )
        for project, role in visible_projects
    ]


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project_route(
    payload: ProjectCreate,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> ProjectRead:
    project, role = create_project(
        session,
        identity,
        name=payload.name,
        domain=payload.domain,
        description=payload.description,
    )
    return _project_read(project, role)


@router.get("/{project_id}", response_model=ProjectRead)
def read_project(
    project_id: UUID,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> ProjectRead:
    """Read a project only when the caller has an explicit membership."""
    project, role = get_project(session, identity, project_id)
    return _project_read(project, role)


@router.get("/{project_id}/templates/{template_id}", response_model=PipelineTemplateRead)
def read_project_pipeline_template(
    project_id: UUID,
    template_id: str,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> PipelineTemplateRead:
    """Return a fixed template contract only to an explicit member of the demo project."""
    project, _role = get_project(session, identity, project_id)
    if project.id != DEMO_PROJECT_ID or template_id != DEMO_PIPELINE_TEMPLATE:
        raise AppError(404, "TEMPLATE_NOT_FOUND")

    try:
        loaded = load_template_manifest(template_id)
    except TemplateRegistryError as exc:
        raise AppError(503, "TEMPLATE_REGISTRY_UNAVAILABLE") from exc

    return PipelineTemplateRead(
        **loaded.manifest.model_dump(),
        manifest_sha256=loaded.sha256,
    )


@router.get(
    "/demo/{project_key}/datasets/{dataset_version}/quality-report",
    response_model=DatasetQualityReportRead,
)
def read_demo_dataset_quality_report(
    project_key: str,
    dataset_version: str,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> DatasetQualityReportRead:
    """Check the fixed registered synthetic manifest for an authenticated project member."""
    if project_key != "demo-research" or dataset_version != DEMO_DATASET_VERSION:
        raise AppError(404, "DATASET_VERSION_NOT_FOUND")

    project, _role = get_project(session, identity, DEMO_PROJECT_ID)
    dataset = session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.project_id == project.id,
            DatasetVersion.version == DEMO_DATASET_VERSION,
        )
    )
    if dataset is None:
        raise AppError(404, "DATASET_VERSION_NOT_FOUND")

    return _quality_report_read(inspect_dataset_manifest(dataset))
