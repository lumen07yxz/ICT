"""Persist and list fixed-template proposals without starting pipeline work."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import DatasetVersion, Project, RunProposal
from app.db.seed_demo import DEMO_PROJECT_ID
from app.errors import AppError
from app.services.template_registry import (
    DEMO_DATASET_VERSION,
    DEMO_PIPELINE_TEMPLATE,
    TemplateContractError,
    TemplateRegistryError,
    load_template_manifest,
    validate_template_values,
)


DEMO_PROJECT_KEY = "demo-research"
PROPOSAL_TTL = timedelta(minutes=15)


def _configuration_hash(
    *,
    project_id: str,
    dataset_version_id: str,
    pipeline_template: str,
    template_version: str,
    template_manifest_sha256: str,
    sample_limit: int,
) -> str:
    """Hash only the canonical fixed configuration, never a secret or user payload."""
    payload = {
        "project_id": project_id,
        "dataset_version_id": dataset_version_id,
        "pipeline_template": pipeline_template,
        "template_version": template_version,
        "template_manifest_sha256": template_manifest_sha256,
        "parameters": {"sample_limit": sample_limit},
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def configuration_hash_for_proposal(session: Session, proposal: RunProposal) -> str:
    """Rebuild the fixed configuration from database records before approving it."""
    project = session.get(Project, proposal.project_id)
    dataset = session.get(DatasetVersion, proposal.dataset_version_id)
    if (
        project is None
        or project.id != DEMO_PROJECT_ID
        or dataset is None
        or dataset.project_id != DEMO_PROJECT_ID
    ):
        raise AppError(409, "PROPOSAL_CONFIG_MISMATCH")

    try:
        template = load_template_manifest(proposal.pipeline_template)
        validate_template_values(
            template.manifest.inputs,
            {"dataset_version": dataset.version},
        )
        validate_template_values(template.manifest.parameters, proposal.parameters)
    except (TemplateContractError, TemplateRegistryError) as exc:
        raise AppError(409, "PROPOSAL_CONFIG_MISMATCH") from exc

    sample_limit = proposal.parameters["sample_limit"]
    return _configuration_hash(
        project_id=str(project.id),
        dataset_version_id=str(dataset.id),
        pipeline_template=proposal.pipeline_template,
        template_version=template.manifest.version,
        template_manifest_sha256=template.sha256,
        sample_limit=sample_limit,
    )


def _existing_proposal(session: Session, idempotency_key: str, config_sha256: str) -> RunProposal | None:
    """Return an identical prior request or reject key reuse with different settings."""
    existing = session.scalar(
        select(RunProposal).where(RunProposal.idempotency_key == idempotency_key)
    )
    if existing is None:
        return None
    if existing.config_sha256 != config_sha256:
        raise AppError(409, "IDEMPOTENCY_CONFLICT")
    return existing


def create_run_proposal(
    session: Session,
    *,
    idempotency_key: str,
    sample_limit: int,
) -> tuple[RunProposal, bool]:
    """Create one pending synthetic proposal, returning whether it was newly inserted."""
    try:
        template = load_template_manifest(DEMO_PIPELINE_TEMPLATE)
        validate_template_values(
            template.manifest.parameters,
            {"sample_limit": sample_limit},
        )
    except TemplateRegistryError as exc:
        raise AppError(503, "TEMPLATE_REGISTRY_UNAVAILABLE") from exc
    except TemplateContractError as exc:
        raise AppError(422, "INVALID_REQUEST") from exc

    project = session.get(Project, DEMO_PROJECT_ID)
    dataset = session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.project_id == DEMO_PROJECT_ID,
            DatasetVersion.version == template.manifest.dataset_version,
        )
    )
    if project is None or dataset is None:
        raise AppError(503, "DEMO_DATASET_NOT_CONFIGURED")

    config_sha256 = _configuration_hash(
        project_id=str(project.id),
        dataset_version_id=str(dataset.id),
        pipeline_template=DEMO_PIPELINE_TEMPLATE,
        template_version=template.manifest.version,
        template_manifest_sha256=template.sha256,
        sample_limit=sample_limit,
    )
    existing = _existing_proposal(session, idempotency_key, config_sha256)
    if existing is not None:
        return existing, False

    now = datetime.now(timezone.utc)
    proposal = RunProposal(
        project_id=project.id,
        dataset_version_id=dataset.id,
        created_by="agentarts-mcp",
        pipeline_template=DEMO_PIPELINE_TEMPLATE,
        parameters={"sample_limit": sample_limit},
        config_sha256=config_sha256,
        idempotency_key=idempotency_key,
        status="pending_approval",
        created_at=now,
        expires_at=now + PROPOSAL_TTL,
    )
    session.add(proposal)
    try:
        session.commit()
    except IntegrityError:
        # A concurrent delivery can win the unique idempotency key; replay that row safely.
        session.rollback()
        existing = _existing_proposal(session, idempotency_key, config_sha256)
        if existing is None:
            raise
        return existing, False

    session.refresh(proposal)
    return proposal, True


def list_visible_run_proposals(session: Session, user_id: str) -> list[RunProposal]:
    """Return proposal rows only from projects with an explicit user membership."""
    from app.db.models import Membership

    statement = (
        select(RunProposal)
        .join(Membership, Membership.project_id == RunProposal.project_id)
        .where(Membership.user_id == user_id)
        .order_by(RunProposal.created_at.desc(), RunProposal.id.desc())
        .limit(100)
    )
    return list(session.scalars(statement))
