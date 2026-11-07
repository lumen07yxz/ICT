"""Idempotent seed data for software integration; contains no medical records."""

from uuid import NAMESPACE_URL, uuid5
import logging
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import DemoIdentity
from app.db.models import DatasetVersion, Membership, Project
from app.db.session import build_engine
from app.services.workspace_catalog import ensure_identity_workspace, ensure_workspace_member


DEMO_PROJECT_ID = uuid5(NAMESPACE_URL, "ict/demo-research")
DEMO_DATASET_ID = uuid5(NAMESPACE_URL, "ict/demo-research/dataset-synthetic-v1")


def seed_demo_project(session: Session) -> Project:
    """Create the fixed synthetic project and its operator/viewer roles once."""
    project = session.get(Project, DEMO_PROJECT_ID)
    if project is None:
        workspace = ensure_identity_workspace(
            session, DemoIdentity(user_id="demo-operator", role="operator")
        )
        project = Project(
            id=DEMO_PROJECT_ID,
            workspace_id=workspace.id,
            name="科研软件合成演示项目",
            domain="general",
            description="仅用于软件接口联调；不含真实数据或科研结果。",
            visibility="demo",
        )
        session.add(project)
        session.flush()

    for user_id, role in (("demo-operator", "operator"), ("demo-viewer", "viewer")):
        membership = session.get(Membership, (DEMO_PROJECT_ID, user_id))
        if membership is None:
            session.add(Membership(project_id=DEMO_PROJECT_ID, user_id=user_id, role=role))
        ensure_workspace_member(
            session,
            workspace_id=project.workspace_id,
            user_id=user_id,
            role=role,
        )

    dataset = session.get(DatasetVersion, DEMO_DATASET_ID)
    if dataset is None:
        dataset = session.scalar(
            select(DatasetVersion).where(
                DatasetVersion.project_id == DEMO_PROJECT_ID,
                DatasetVersion.version == "dataset-synthetic-v1",
            )
        )
    if dataset is None:
        session.add(
            DatasetVersion(
                id=DEMO_DATASET_ID,
                project_id=DEMO_PROJECT_ID,
                version="dataset-synthetic-v1",
                manifest_ref="synthetic://demo-research/dataset-synthetic-v1/manifest",
                schema_ref="synthetic://demo-research/dataset-synthetic-v1/schema",
                source="synthetic",
                license_status="not_applicable",
                split_policy={"type": "synthetic", "research_ready": False},
                created_by="demo-operator",
            )
        )

    session.commit()
    session.refresh(project)
    return project


def main() -> int:
    """Seed the demo after migrations; never create or overwrite schema here."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        engine = build_engine()
    except RuntimeError as exc:
        logging.error("demo_seed_failed error=%s", exc)
        return 2

    try:
        with sessionmaker(bind=engine, expire_on_commit=False)() as session:
            project = seed_demo_project(session)
            logging.info(
                "demo_seed_complete project_id=%s dataset_version=dataset-synthetic-v1",
                project.id,
            )
    except Exception:
        logging.exception("demo_seed_failed error_code=SEED_FAILED")
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
