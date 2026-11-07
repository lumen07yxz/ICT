"""Alembic 空库升级验收，使用临时 SQLite，不触碰共享数据。"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class MigrationTests(unittest.TestCase):
    def test_upgrade_from_empty_database_creates_model_tables(self) -> None:
        from app.db.models import Base

        with tempfile.TemporaryDirectory() as directory:
            database_file = Path(directory) / "migration-test.db"
            database_url = f"sqlite:///{database_file.as_posix()}"
            config = Config(str(BACKEND_DIR / "alembic.ini"))

            with patch.dict(os.environ, {"DATABASE_URL": database_url}):
                command.upgrade(config, "head")

            engine = create_engine(database_url)
            try:
                actual_tables = set(inspect(engine).get_table_names())
            finally:
                engine.dispose()

        self.assertTrue(set(Base.metadata.tables).issubset(actual_tables))
        self.assertIn("alembic_version", actual_tables)
        self.assertIn("run_events", actual_tables)

    def test_existing_pending_proposals_receive_unique_trace_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_file = Path(directory) / "migration-existing-proposal.db"
            database_url = f"sqlite:///{database_file.as_posix()}"
            config = Config(str(BACKEND_DIR / "alembic.ini"))
            with patch.dict(os.environ, {"DATABASE_URL": database_url}):
                command.upgrade(config, "0002_run_proposals")
                engine = create_engine(database_url)
                proposal_ids = [uuid4().hex, uuid4().hex]
                now = datetime.now(timezone.utc)
                try:
                    with engine.begin() as connection:
                        for index, proposal_id in enumerate(proposal_ids):
                            connection.execute(
                                text(
                                    """
                                    INSERT INTO run_proposals (
                                        id, project_id, dataset_version_id, created_by,
                                        pipeline_template, parameters, config_sha256,
                                        idempotency_key, status, created_at, expires_at
                                    ) VALUES (
                                        :id, :project, :dataset, 'agentarts-mcp',
                                        'research-smoke-v1', '{"sample_limit": 1}', :hash,
                                        :key, 'pending_approval', :created, :expires
                                    )
                                    """
                                ),
                                {
                                    "id": proposal_id,
                                    "project": uuid4().hex,
                                    "dataset": uuid4().hex,
                                    "hash": "a" * 64,
                                    "key": str(index + 1) * 64,
                                    "created": now.isoformat(),
                                    "expires": (now + timedelta(minutes=15)).isoformat(),
                                },
                            )
                finally:
                    engine.dispose()

                with patch.dict(os.environ, {"DATABASE_URL": database_url}):
                    command.upgrade(config, "head")
                engine = create_engine(database_url)
                try:
                    with engine.connect() as connection:
                        trace_ids = connection.execute(
                            text(
                                "SELECT trace_id FROM run_proposals ORDER BY id"
                            )
                        ).scalars().all()
                finally:
                    engine.dispose()

        self.assertEqual(len(trace_ids), 2)
        self.assertTrue(all(len(trace_id) == 36 for trace_id in trace_ids))
        self.assertEqual(len(set(trace_ids)), 2)

    def test_upgrade_backfills_only_statuses_supported_by_historical_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_file = Path(directory) / "migration-run-events.db"
            database_url = f"sqlite:///{database_file.as_posix()}"
            config = Config(str(BACKEND_DIR / "alembic.ini"))
            with patch.dict(os.environ, {"DATABASE_URL": database_url}):
                command.upgrade(config, "0004_generic_quality_gate")

            engine = create_engine(database_url)
            now = datetime.now(timezone.utc)
            project_id, dataset_id = uuid4(), uuid4()
            successful_proposal_id, failed_proposal_id = uuid4(), uuid4()
            successful_trace_id, failed_trace_id = str(uuid4()), str(uuid4())
            successful_run_id, failed_run_id = uuid4(), uuid4()
            try:
                with engine.begin() as connection:
                    connection.execute(
                        text("INSERT INTO projects (id, name, domain) VALUES (:id, 'Migration fixture', 'general')"),
                        {"id": project_id.hex},
                    )
                    connection.execute(
                        text("INSERT INTO memberships (project_id, user_id, role) VALUES (:project, 'migration-operator', 'operator')"),
                        {"project": project_id.hex},
                    )
                    connection.execute(
                        text(
                            "INSERT INTO dataset_versions "
                            "(id, project_id, version, manifest_ref, schema_ref, source, license_status, split_policy, created_by) "
                            "VALUES (:id, :project, 'v1', 'manifest.json', 'schema.json', 'migration fixture', 'approved', '{}', 'migration-test')"
                        ),
                        {"id": dataset_id.hex, "project": project_id.hex},
                    )
                    for index, proposal_id in enumerate((successful_proposal_id, failed_proposal_id)):
                        trace_id = successful_trace_id if index == 0 else failed_trace_id
                        config_hash = "a" * 64 if index == 0 else "b" * 64
                        connection.execute(
                            text(
                                "INSERT INTO run_proposals "
                                "(id, project_id, dataset_version_id, created_by, pipeline_template, parameters, "
                                "config_sha256, idempotency_key, status, created_at, expires_at, trace_id, approved_by, approved_at) "
                                "VALUES (:id, :project, :dataset, 'migration-test', 'research-smoke-v1', "
                                ":parameters, :hash, :key, 'approved', :created, :expires, :trace, 'migration-operator', :approved)"
                            ),
                            {
                                "id": proposal_id.hex,
                                "project": project_id.hex,
                                "dataset": dataset_id.hex,
                                "parameters": '{"sample_limit": 7}',
                                "hash": config_hash,
                                "key": str(index + 1) * 64,
                                "created": now.isoformat(),
                                "expires": (now + timedelta(minutes=15)).isoformat(),
                                "trace": trace_id,
                                "approved": now.isoformat(),
                            },
                        )
                    connection.execute(
                        text(
                            "INSERT INTO runs "
                            "(id, proposal_id, project_id, dataset_version_id, trace_id, pipeline_template, parameters, "
                            "config_sha256, status, error_code, created_at, started_at, finished_at) "
                            "VALUES (:id, :proposal, :project, :dataset, :trace, 'research-smoke-v1', "
                            ":parameters, :hash, :status, :error, :created, :started, :finished)"
                        ),
                        [
                            {
                                "id": successful_run_id.hex,
                                "proposal": successful_proposal_id.hex,
                                "project": project_id.hex,
                                "dataset": dataset_id.hex,
                                "trace": successful_trace_id,
                                "parameters": '{"sample_limit": 7}',
                                "hash": "a" * 64,
                                "status": "succeeded",
                                "error": None,
                                "created": now.isoformat(),
                                "started": (now + timedelta(seconds=1)).isoformat(),
                                "finished": (now + timedelta(seconds=2)).isoformat(),
                            },
                            {
                                "id": failed_run_id.hex,
                                "proposal": failed_proposal_id.hex,
                                "project": project_id.hex,
                                "dataset": dataset_id.hex,
                                "trace": failed_trace_id,
                                "parameters": '{"sample_limit": 7}',
                                "hash": "b" * 64,
                                "status": "failed",
                                "error": "QUEUE_UNAVAILABLE",
                                "created": now.isoformat(),
                                "started": None,
                                "finished": (now + timedelta(seconds=1)).isoformat(),
                            },
                        ],
                    )
            finally:
                engine.dispose()

            with patch.dict(os.environ, {"DATABASE_URL": database_url}):
                command.upgrade(config, "head")

            engine = create_engine(database_url)
            try:
                with engine.connect() as connection:
                    successful_events = connection.execute(
                        text("SELECT sequence, status FROM run_events WHERE run_id = :run_id ORDER BY sequence"),
                        {"run_id": successful_run_id.hex},
                    ).all()
                    failed_events = connection.execute(
                        text("SELECT sequence, status, error_code FROM run_events WHERE run_id = :run_id ORDER BY sequence"),
                        {"run_id": failed_run_id.hex},
                    ).all()
            finally:
                engine.dispose()

        self.assertEqual([(row.sequence, row.status) for row in successful_events], [
            (1, "queued"), (2, "running"), (3, "succeeded")
        ])
        self.assertEqual([(row.sequence, row.status, row.error_code) for row in failed_events], [
            (1, "queued", None), (3, "failed", "QUEUE_UNAVAILABLE")
        ])

    def test_workspace_ownership_migration_backfills_existing_projects_and_workflows(self) -> None:
        """Upgrade a populated pre-workspace database without losing legacy ownership."""
        with tempfile.TemporaryDirectory() as directory:
            database_file = Path(directory) / "migration-workspace-backfill.db"
            database_url = f"sqlite:///{database_file.as_posix()}"
            config = Config(str(BACKEND_DIR / "alembic.ini"))
            with patch.dict(os.environ, {"DATABASE_URL": database_url}):
                command.upgrade(config, "0006_project_workflows")

            engine = create_engine(database_url)
            user_operator_a = "legacy-operator-a"
            user_operator_b = "legacy-operator-b"
            user_shared_viewer = "legacy-shared-viewer"
            project_a, project_b, orphan_project = (uuid4() for _ in range(3))
            workflow_a, workflow_b, orphan_workflow = (uuid4() for _ in range(3))
            try:
                with engine.begin() as connection:
                    for project_id, name in (
                        (project_a, "Legacy Project A"),
                        (project_b, "Legacy Project B"),
                        (orphan_project, "Legacy Orphan Project"),
                    ):
                        connection.execute(
                            text("INSERT INTO projects (id, name, domain) VALUES (:id, :name, 'general')"),
                            {"id": project_id.hex, "name": name},
                        )
                    connection.execute(
                        text("INSERT INTO memberships (project_id, user_id, role) VALUES (:project, :user, :role)"),
                        [
                            {"project": project_a.hex, "user": user_operator_a, "role": "operator"},
                            {"project": project_a.hex, "user": user_shared_viewer, "role": "viewer"},
                            {"project": project_b.hex, "user": user_operator_b, "role": "operator"},
                            {"project": project_b.hex, "user": user_shared_viewer, "role": "viewer"},
                        ],
                    )
                    for workflow_id, project_id, name in (
                        (workflow_a, project_a, "Legacy Workflow A"),
                        (workflow_b, project_b, "Legacy Workflow B"),
                        (orphan_workflow, orphan_project, "Legacy Orphan Workflow"),
                    ):
                        connection.execute(
                            text(
                                "INSERT INTO workflows "
                                "(id, project_id, name, description, graph, revision, current_version, created_by, updated_by) "
                                "VALUES (:id, :project, :name, 'legacy description', '{\"nodes\":[],\"edges\":[]}', 2, 0, 'migration-test', 'migration-test')"
                            ),
                            {"id": workflow_id.hex, "project": project_id.hex, "name": name},
                        )
            finally:
                engine.dispose()

            with patch.dict(os.environ, {"DATABASE_URL": database_url}):
                command.upgrade(config, "head")

            from app.db.session import build_engine

            engine = build_engine(database_url)
            try:
                with engine.connect() as connection:
                    project_rows = connection.execute(
                        text("SELECT id, workspace_id FROM projects")
                    ).all()
                    workflow_rows = connection.execute(
                        text("SELECT id, project_id, workspace_id, owner_type, name, description FROM workflows")
                    ).all()
                    workspace_rows = connection.execute(
                        text("SELECT id, created_by, name FROM workspaces")
                    ).all()
                    workspace_membership_rows = connection.execute(
                        text("SELECT workspace_id, user_id, role FROM workspace_memberships")
                    ).all()
                expected_workspace_a = uuid5(NAMESPACE_URL, f"ict/workspaces/{user_operator_a}").hex
                expected_workspace_c = uuid5(NAMESPACE_URL, f"ict/workspaces/{user_operator_b}").hex
                invalid_workflow_sql = text(
                    "INSERT INTO workflows "
                    "(id, workspace_id, owner_type, project_id, reproduction_task_id, name, description, graph, "
                    "revision, current_version, created_by, updated_by) "
                    "VALUES (:id, :workspace, :owner, :project, :reproduction, 'Invalid', '', '{}', 1, 0, 'test', 'test')"
                )
                with self.assertRaises(IntegrityError):
                    with engine.begin() as connection:
                        connection.execute(
                            invalid_workflow_sql,
                            {
                                "id": uuid4().hex,
                                "workspace": expected_workspace_a,
                                "owner": "project",
                                "project": None,
                                "reproduction": None,
                            },
                        )
                with self.assertRaises(IntegrityError):
                    with engine.begin() as connection:
                        connection.execute(
                            invalid_workflow_sql,
                            {
                                "id": uuid4().hex,
                                "workspace": expected_workspace_c,
                                "owner": "project",
                                "project": project_a.hex,
                                "reproduction": None,
                            },
                        )
            finally:
                engine.dispose()

        projects_by_id = {UUID(str(row.id)).hex: UUID(str(row.workspace_id)).hex for row in project_rows}
        expected_workspace_b = uuid5(NAMESPACE_URL, f"ict/workspaces/{user_shared_viewer}").hex
        expected_orphan_workspace = uuid5(
            NAMESPACE_URL, f"ict/orphan-project-workspace/{orphan_project}"
        ).hex
        self.assertEqual(projects_by_id, {
            project_a.hex: expected_workspace_a,
            project_b.hex: expected_workspace_c,
            orphan_project.hex: expected_orphan_workspace,
        })

        workflows_by_id = {UUID(str(row.id)).hex: row for row in workflow_rows}
        self.assertEqual(
            (workflows_by_id[workflow_a.hex].owner_type, UUID(str(workflows_by_id[workflow_a.hex].workspace_id)).hex),
            ("project", expected_workspace_a),
        )
        self.assertEqual(
            (workflows_by_id[workflow_b.hex].owner_type, UUID(str(workflows_by_id[workflow_b.hex].workspace_id)).hex),
            ("project", expected_workspace_c),
        )
        self.assertEqual(
            (workflows_by_id[orphan_workflow.hex].owner_type, UUID(str(workflows_by_id[orphan_workflow.hex].workspace_id)).hex),
            ("project", expected_orphan_workspace),
        )
        self.assertEqual(workflows_by_id[workflow_a.hex].name, "Legacy Workflow A")
        self.assertEqual(workflows_by_id[workflow_a.hex].description, "legacy description")

        workspaces_by_id = {UUID(str(row.id)).hex: (row.created_by, row.name) for row in workspace_rows}
        self.assertEqual(len(workspaces_by_id), 4)
        self.assertEqual(workspaces_by_id[expected_orphan_workspace], ("migration", "归档项目工作空间"))
        workspace_memberships = {
            (UUID(str(row.workspace_id)).hex, row.user_id, row.role)
            for row in workspace_membership_rows
        }
        self.assertEqual(workspace_memberships, {
            (expected_workspace_a, user_operator_a, "operator"),
            (expected_workspace_a, user_shared_viewer, "viewer"),
            (expected_workspace_b, user_shared_viewer, "viewer"),
            (expected_workspace_c, user_operator_b, "operator"),
            (expected_workspace_c, user_shared_viewer, "viewer"),
        })


if __name__ == "__main__":
    unittest.main()
