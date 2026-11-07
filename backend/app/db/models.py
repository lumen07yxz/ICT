"""SQLAlchemy schema for workspaces, projects, reproductions, and workflows."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    JSON,
    Index,
    Integer,
    String,
    Table,
    Column,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base metadata shared by Alembic and database tests."""


dataset_assets = Table(
    "dataset_assets",
    Base.metadata,
    Column(
        "dataset_version_id",
        Uuid(as_uuid=True),
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "asset_id",
        Uuid(as_uuid=True),
        ForeignKey("assets.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
)


class Workspace(Base):
    """Shared isolation boundary for projects and independent reproduction tasks."""

    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    memberships: Mapped[list["WorkspaceMembership"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="workspace", foreign_keys="Project.workspace_id"
    )
    reproduction_tasks: Mapped[list["ReproductionTask"]] = relationship(
        back_populates="workspace", foreign_keys="ReproductionTask.workspace_id"
    )


class WorkspaceMembership(Base):
    """Workspace-level access used for independent research objects."""

    __tablename__ = "workspace_memberships"
    __table_args__ = (CheckConstraint("role IN ('operator', 'viewer')", name="ck_workspace_memberships_role"),)

    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    workspace: Mapped[Workspace] = relationship(back_populates="memberships")


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint(
            "visibility IN ('private', 'demo')",
            name="ck_projects_visibility",
        ),
        UniqueConstraint("id", "workspace_id", name="uq_projects_id_workspace"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    domain: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    visibility: Mapped[str] = mapped_column(
        String(16), nullable=False, default="private", server_default="private"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    workspace: Mapped[Workspace] = relationship(
        back_populates="projects", foreign_keys=[workspace_id]
    )
    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    assets: Mapped[list["Asset"]] = relationship(back_populates="project")
    dataset_versions: Mapped[list["DatasetVersion"]] = relationship(back_populates="project")
    workflows: Mapped[list["Workflow"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", foreign_keys="Workflow.project_id"
    )


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_memberships_project_user"),
        CheckConstraint("role IN ('operator', 'viewer')", name="ck_memberships_role"),
    )

    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped[Project] = relationship(back_populates="memberships")


class ReproductionTask(Base):
    """Independent paper-reproduction or experiment-verification task."""

    __tablename__ = "reproduction_tasks"
    __table_args__ = (
        UniqueConstraint("id", "workspace_id", name="uq_reproduction_tasks_id_workspace"),
        CheckConstraint("kind IN ('paper', 'experiment')", name="ck_reproduction_tasks_kind"),
        CheckConstraint(
            "status IN ('preparation', 'insufficient_conditions', 'ready_to_run', 'running', "
            "'awaiting_review', 'conforms', 'differs', 'undetermined')",
            name="ck_reproduction_tasks_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    linked_project_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    claim: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    baseline: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    criteria_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="preparation", server_default="preparation"
    )
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped[Workspace] = relationship(
        back_populates="reproduction_tasks", foreign_keys=[workspace_id]
    )
    workflows: Mapped[list["Workflow"]] = relationship(
        back_populates="reproduction_task",
        cascade="all, delete-orphan",
        foreign_keys="Workflow.reproduction_task_id",
    )


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("project_id", "sha256", name="uq_assets_project_sha256"),
        CheckConstraint("length(sha256) = 64", name="ck_assets_sha256_length"),
        CheckConstraint("size_bytes > 0", name="ck_assets_size_positive"),
        CheckConstraint(
            "privacy_level IN ('public', 'deidentified', 'restricted')",
            name="ck_assets_privacy_level",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    license_status: Mapped[str] = mapped_column(String(32), nullable=False)
    privacy_level: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped[Project] = relationship(back_populates="assets")


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_dataset_versions_project_version"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    schema_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    license_status: Mapped[str] = mapped_column(String(32), nullable=False)
    split_policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped[Project] = relationship(back_populates="dataset_versions")
    assets: Mapped[list[Asset]] = relationship(secondary=dataset_assets)


class Workflow(Base):
    """Mutable project- or reproduction-owned draft; snapshots live separately."""

    __tablename__ = "workflows"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_workflows_revision_positive"),
        CheckConstraint("current_version >= 0", name="ck_workflows_current_version_nonnegative"),
        CheckConstraint(
            "(owner_type = 'project' AND project_id IS NOT NULL AND reproduction_task_id IS NULL) OR "
            "(owner_type = 'reproduction' AND reproduction_task_id IS NOT NULL AND project_id IS NULL)",
            name="ck_workflows_exactly_one_owner",
        ),
        ForeignKeyConstraint(
            ["project_id", "workspace_id"],
            ["projects.id", "projects.workspace_id"],
            name="fk_workflows_project_workspace",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["reproduction_task_id", "workspace_id"],
            ["reproduction_tasks.id", "reproduction_tasks.workspace_id"],
            name="fk_workflows_reproduction_workspace",
            ondelete="CASCADE",
        ),
        Index("ix_workflows_project_updated", "project_id", "updated_at"),
        Index("ix_workflows_reproduction_updated", "reproduction_task_id", "updated_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    owner_type: Mapped[str] = mapped_column(String(16), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    reproduction_task_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    graph: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped[Workspace] = relationship(foreign_keys=[workspace_id])
    project: Mapped[Project | None] = relationship(
        back_populates="workflows", foreign_keys=[project_id]
    )
    reproduction_task: Mapped[ReproductionTask | None] = relationship(
        back_populates="workflows", foreign_keys=[reproduction_task_id]
    )
    versions: Mapped[list["WorkflowVersion"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan", order_by="WorkflowVersion.version"
    )

    @property
    def owner_id(self) -> UUID:
        """Expose V4.0 owner_id while storage uses enforceable dual foreign keys."""
        owner_id = self.project_id if self.owner_type == "project" else self.reproduction_task_id
        if owner_id is None:
            raise ValueError("workflow owner constraint is violated")
        return owner_id


class WorkflowVersion(Base):
    """Immutable workflow metadata and graph snapshot created from a valid draft."""

    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint("workflow_id", "version", name="uq_workflow_versions_workflow_version"),
        CheckConstraint("version >= 1", name="ck_workflow_versions_version_positive"),
        CheckConstraint("length(content_hash) = 64", name="ck_workflow_versions_hash_length"),
        Index("ix_workflow_versions_workflow_created", "workflow_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workflow_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nullable so pre-metadata snapshots remain readable without inventing old values.
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    graph: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    workflow: Mapped[Workflow] = relationship(back_populates="versions")


class RunProposal(Base):
    """A fixed synthetic pipeline request and its authenticated approval record."""

    __tablename__ = "run_proposals"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_run_proposals_idempotency_key"),
        UniqueConstraint("trace_id", name="uq_run_proposals_trace_id"),
        CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'expired', 'cancelled')",
            name="ck_run_proposals_status",
        ),
        CheckConstraint("length(config_sha256) = 64", name="ck_run_proposals_config_sha256_length"),
        CheckConstraint("length(idempotency_key) = 64", name="ck_run_proposals_idempotency_key_length"),
        Index("ix_run_proposals_project_created", "project_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    dataset_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("dataset_versions.id", ondelete="RESTRICT"), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(80), nullable=False)
    pipeline_template: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str] = mapped_column(
        String(36), nullable=False, default=lambda: str(uuid4())
    )
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pending_approval", server_default="pending_approval"
    )
    approved_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    run: Mapped["Run | None"] = relationship(back_populates="proposal", uselist=False)


class Run(Base):
    """One immutable execution record created only after an operator approves a proposal."""

    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("proposal_id", name="uq_runs_proposal_id"),
        UniqueConstraint("trace_id", name="uq_runs_trace_id"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_runs_status",
        ),
        CheckConstraint("length(config_sha256) = 64", name="ck_runs_config_sha256_length"),
        CheckConstraint(
            "quality_status IS NULL OR quality_status IN ('success', 'warning')",
            name="ck_runs_quality_status",
        ),
        CheckConstraint(
            "quality_report_sha256 IS NULL OR length(quality_report_sha256) = 64",
            name="ck_runs_quality_report_sha256_length",
        ),
        CheckConstraint(
            "(quality_status IS NULL AND quality_rule_set_version IS NULL AND quality_report_sha256 IS NULL) "
            "OR (quality_status IS NOT NULL AND quality_rule_set_version IS NOT NULL AND quality_report_sha256 IS NOT NULL)",
            name="ck_runs_quality_snapshot_complete",
        ),
        Index("ix_runs_project_created", "project_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    proposal_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("run_proposals.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    dataset_version_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("dataset_versions.id", ondelete="RESTRICT"), nullable=False
    )
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    pipeline_template: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    quality_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quality_rule_set_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quality_report_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued", server_default="queued")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    proposal: Mapped[RunProposal] = relationship(back_populates="run")


class RunEvent(Base):
    """Append-only fixed status history for one synthetic run."""

    __tablename__ = "run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence", name="uq_run_events_run_sequence"),
        CheckConstraint(
            "(sequence = 1 AND status = 'queued') OR "
            "(sequence = 2 AND status = 'running') OR "
            "(sequence = 3 AND status IN ('succeeded', 'failed'))",
            name="ck_run_events_sequence_status",
        ),
        CheckConstraint(
            "error_code IS NULL OR error_code IN ('QUEUE_UNAVAILABLE', 'WORKER_EXECUTION_FAILED')",
            name="ck_run_events_error_code",
        ),
        CheckConstraint(
            "status = 'failed' OR error_code IS NULL",
            name="ck_run_events_error_only_on_failure",
        ),
        Index("ix_run_events_run_sequence", "run_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
