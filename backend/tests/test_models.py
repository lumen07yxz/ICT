"""W1 数据库基础表与核心约束的验收。"""

import sys
import unittest
from pathlib import Path
from uuid import uuid4

from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class DatabaseModelTests(unittest.TestCase):
    def setUp(self) -> None:
        from app.db.models import Base
        from app.db.session import build_engine

        self.engine = build_engine("sqlite://")
        Base.metadata.create_all(self.engine)

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_core_project_and_dataset_tables_are_created(self) -> None:
        tables = set(inspect(self.engine).get_table_names())

        self.assertTrue(
            {
                "projects",
                "memberships",
                "assets",
                "dataset_versions",
                "dataset_assets",
            }.issubset(tables)
        )

    def test_membership_roles_are_limited_and_unique_per_project_user(self) -> None:
        from app.db.models import Membership, Project, Workspace

        project_id = uuid4()
        workspace = Workspace(id=uuid4(), name="Model test", created_by="test")
        with Session(self.engine) as session:
            session.add(Project(id=project_id, workspace=workspace, name="Demo", domain="general"))
            session.add(Membership(project_id=project_id, user_id="operator-1", role="operator"))
            session.commit()

            session.add(Membership(project_id=project_id, user_id="operator-1", role="viewer"))
            with self.assertRaises(IntegrityError):
                session.commit()
            session.rollback()

            session.add(Membership(project_id=project_id, user_id="viewer-1", role="admin"))
            with self.assertRaises(IntegrityError):
                session.commit()

    def test_dataset_version_is_unique_within_a_project(self) -> None:
        from app.db.models import DatasetVersion, Project, Workspace

        project_id = uuid4()
        workspace = Workspace(id=uuid4(), name="Model test", created_by="test")
        with Session(self.engine) as session:
            session.add(Project(id=project_id, workspace=workspace, name="Demo", domain="general"))
            session.add(
                DatasetVersion(
                    id=uuid4(),
                    project_id=project_id,
                    version="synthetic-v1",
                    source="synthetic",
                    license_status="not_applicable",
                    manifest_ref="synthetic://demo/manifest-v1",
                    schema_ref="synthetic://demo/schema-v1",
                    split_policy={"type": "synthetic"},
                    created_by="operator-1",
                )
            )
            session.commit()

            session.add(
                DatasetVersion(
                    id=uuid4(),
                    project_id=project_id,
                    version="synthetic-v1",
                    source="synthetic",
                    license_status="not_applicable",
                    manifest_ref="synthetic://demo/manifest-v2",
                    schema_ref="synthetic://demo/schema-v2",
                    split_policy={"type": "synthetic"},
                    created_by="operator-1",
                )
            )
            with self.assertRaises(IntegrityError):
                session.commit()


if __name__ == "__main__":
    unittest.main()
