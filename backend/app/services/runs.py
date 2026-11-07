"""Approval, membership-scoped run reads, and the fixed synthetic smoke job."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import hmac
import logging
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import DemoIdentity
from app.db.models import DatasetVersion, Membership, Run, RunEvent, RunProposal
from app.errors import AppError
from app.services.dataset_quality import inspect_dataset_manifest
from app.services.run_proposals import configuration_hash_for_proposal
from app.services.template_registry import (
    DEMO_PIPELINE_TEMPLATE,
    TemplateRegistryError,
    load_template_manifest,
    validate_template_values,
)


logger = logging.getLogger("ict.worker")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
logger.propagate = False


def _add_run_event(
    session: Session,
    run: Run,
    *,
    sequence: int,
    status: str,
    occurred_at: datetime,
    error_code: str | None = None,
) -> None:
    """Add one fixed lifecycle event in the same transaction as its run update."""
    session.add(
        RunEvent(
            run_id=run.id,
            sequence=sequence,
            status=status,
            error_code=error_code,
            occurred_at=occurred_at,
        )
    )


def approve_run_proposal(
    session: Session,
    identity: DemoIdentity,
    proposal_id: UUID,
    *,
    now: datetime | None = None,
) -> tuple[Run, bool]:
    """Approve one visible, fixed proposal and atomically create its unique queued run."""
    row = session.execute(
        select(RunProposal, Membership.role)
        .join(Membership, Membership.project_id == RunProposal.project_id)
        .where(RunProposal.id == proposal_id, Membership.user_id == identity.user_id)
        .with_for_update()
    ).one_or_none()
    if row is None:
        raise AppError(404, "PROPOSAL_NOT_FOUND")

    proposal, member_role = row
    if identity.role != "operator" or member_role != "operator":
        raise AppError(403, "FORBIDDEN")

    existing = session.scalar(select(Run).where(Run.proposal_id == proposal.id))
    if existing is not None:
        return existing, False
    if proposal.status != "pending_approval":
        if proposal.status == "expired":
            raise AppError(409, "PROPOSAL_EXPIRED")
        raise AppError(409, "PROPOSAL_NOT_APPROVABLE")

    current = now or datetime.now(timezone.utc)
    expires_at = proposal.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= current:
        proposal.status = "expired"
        session.commit()
        raise AppError(409, "PROPOSAL_EXPIRED")

    expected_hash = configuration_hash_for_proposal(session, proposal)
    if not hmac.compare_digest(expected_hash, proposal.config_sha256):
        raise AppError(409, "PROPOSAL_CONFIG_MISMATCH")

    dataset = session.get(DatasetVersion, proposal.dataset_version_id)
    if dataset is None:
        raise AppError(409, "QUALITY_SOURCE_NOT_SUPPORTED")
    quality_report = inspect_dataset_manifest(dataset)
    if quality_report.status == "blocker":
        raise AppError(409, "DATA_QUALITY_BLOCKED")

    proposal.status = "approved"
    proposal.approved_by = identity.user_id
    proposal.approved_at = current
    run = Run(
        proposal_id=proposal.id,
        project_id=proposal.project_id,
        dataset_version_id=proposal.dataset_version_id,
        trace_id=proposal.trace_id,
        pipeline_template=proposal.pipeline_template,
        parameters=dict(proposal.parameters),
        config_sha256=proposal.config_sha256,
        quality_status=quality_report.status,
        quality_rule_set_version=quality_report.rule_set_version,
        quality_report_sha256=quality_report.manifest_sha256,
        status="queued",
        created_at=current,
    )
    session.add(run)
    try:
        # Flush the generated run ID while preserving one atomic approval transaction.
        session.flush()
        _add_run_event(
            session,
            run,
            sequence=1,
            status="queued",
            occurred_at=current,
        )
        session.commit()
    except IntegrityError:
        # The unique proposal constraint makes concurrent approval safe to replay.
        session.rollback()
        existing = session.scalar(select(Run).where(Run.proposal_id == proposal_id))
        if existing is None:
            raise
        return existing, False

    session.refresh(run)
    return run, True


def mark_run_dispatch_failed(session: Session, run_id: UUID, *, now: datetime | None = None) -> Run | None:
    """Make queue publication errors visible through the same four-state run contract."""
    finished_at = now or datetime.now(timezone.utc)
    failed_id = session.scalar(
        update(Run)
        .where(Run.id == run_id, Run.status == "queued")
        .values(
            status="failed",
            error_code="QUEUE_UNAVAILABLE",
            finished_at=finished_at,
        )
        .returning(Run.id)
    )
    if failed_id is None:
        return session.get(Run, run_id)
    run = session.get(Run, run_id)
    if run is None:
        return None
    _add_run_event(
        session,
        run,
        sequence=3,
        status="failed",
        occurred_at=finished_at,
        error_code=run.error_code,
    )
    session.commit()
    session.refresh(run)
    return run


def list_visible_runs(session: Session, user_id: str, project_id: UUID | None = None) -> list[Run]:
    """List member-visible runs, optionally narrowed without crossing project access."""
    statement = (
        select(Run)
        .join(Membership, Membership.project_id == Run.project_id)
        .where(Membership.user_id == user_id)
        .order_by(Run.created_at.desc(), Run.id.desc())
    )
    if project_id is not None:
        statement = statement.where(Run.project_id == project_id)
    statement = statement.limit(100)
    return list(session.scalars(statement))


def get_visible_run(session: Session, user_id: str, run_id: UUID) -> Run:
    """Return one run only after checking the caller's project membership."""
    run = session.scalar(
        select(Run)
        .join(Membership, Membership.project_id == Run.project_id)
        .where(Run.id == run_id, Membership.user_id == user_id)
    )
    if run is None:
        raise AppError(404, "RUN_NOT_FOUND")
    return run


def list_visible_run_events(session: Session, user_id: str, run_id: UUID) -> list[RunEvent]:
    """Read an ordered event history only after checking run project membership."""
    get_visible_run(session, user_id, run_id)
    return list(
        session.scalars(
            select(RunEvent)
            .where(RunEvent.run_id == run_id)
            .order_by(RunEvent.sequence.asc())
        )
    )


def calculate_smoke_result(
    parameters: dict[str, object],
    *,
    template_id: str = DEMO_PIPELINE_TEMPLATE,
) -> dict[str, object]:
    """Return a deterministic integration result without reading data or running science."""
    try:
        template = load_template_manifest(template_id)
        validate_template_values(template.manifest.parameters, parameters)
    except TemplateRegistryError as exc:
        raise ValueError("fixed synthetic template is unavailable") from exc

    result = {
        "task": "synthetic_smoke",
        "processed_count": parameters["sample_limit"],
        "synthetic_only": True,
        "research_ready": False,
        "message": "集成冒烟任务完成。",
    }
    validate_template_values(template.manifest.outputs, result)
    return result


def execute_smoke_run(
    session_factory: Callable[[], Session],
    run_id: UUID,
) -> bool:
    """Run one queued smoke item; duplicate deliveries cannot repeat terminal work."""
    with session_factory() as session:
        started_at = datetime.now(timezone.utc)
        claimed_id = session.scalar(
            update(Run)
            .where(Run.id == run_id, Run.status == "queued")
            .values(status="running", started_at=started_at)
            .returning(Run.id)
        )
        if claimed_id is None:
            return False
        run = session.get(Run, run_id)
        if run is None:
            return False
        trace_id = run.trace_id
        _add_run_event(
            session,
            run,
            sequence=2,
            status="running",
            occurred_at=started_at,
        )
        session.commit()

    logger.info("run_worker_started run_id=%s trace_id=%s", run_id, trace_id)
    try:
        with session_factory() as session:
            run = session.get(Run, run_id)
            if run is None:
                return False
            proposal = session.get(RunProposal, run.proposal_id)
            if (
                proposal is None
                or proposal.pipeline_template != run.pipeline_template
                or not hmac.compare_digest(proposal.config_sha256, run.config_sha256)
            ):
                raise ValueError("queued run no longer matches its approved proposal")
            expected_hash = configuration_hash_for_proposal(session, proposal)
            if not hmac.compare_digest(expected_hash, run.config_sha256):
                raise ValueError("queued run no longer matches its approved template")
            result = calculate_smoke_result(
                dict(run.parameters),
                template_id=run.pipeline_template,
            )
    except Exception as exc:
        with session_factory() as session:
            run = session.get(Run, run_id)
            if run is not None and run.status == "running":
                run.status = "failed"
                run.error_code = "WORKER_EXECUTION_FAILED"
                finished_at = datetime.now(timezone.utc)
                run.finished_at = finished_at
                _add_run_event(
                    session,
                    run,
                    sequence=3,
                    status="failed",
                    occurred_at=finished_at,
                    error_code=run.error_code,
                )
                session.commit()
        logger.error(
            "run_worker_failed run_id=%s trace_id=%s error_code=WORKER_EXECUTION_FAILED error_type=%s",
            run_id,
            trace_id,
            type(exc).__name__,
        )
        return False

    with session_factory() as session:
        run = session.get(Run, run_id)
        if run is None or run.status != "running":
            return False
        run.status = "succeeded"
        run.result = result
        finished_at = datetime.now(timezone.utc)
        run.finished_at = finished_at
        _add_run_event(
            session,
            run,
            sequence=3,
            status="succeeded",
            occurred_at=finished_at,
        )
        session.commit()
    logger.info("run_worker_succeeded run_id=%s trace_id=%s", run_id, trace_id)
    return True
