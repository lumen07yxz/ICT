"""Worker tests cover deterministic execution and safe terminal transitions."""

import sys
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class SmokeWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        from app.db.models import Base
        from app.db.seed_demo import seed_demo_project

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        with self.session_factory() as session:
            self.project = seed_demo_project(session)
            self.dataset = self.project.dataset_versions[0]
            self.run_id = self._make_run(session)

    def tearDown(self) -> None:
        self.engine.dispose()

    def _make_run(self, session):
        from app.db.models import Run, RunEvent, RunProposal

        now = datetime.now(timezone.utc)
        proposal = RunProposal(
            project_id=self.project.id,
            dataset_version_id=self.dataset.id,
            created_by="agentarts-mcp",
            pipeline_template="research-smoke-v1",
            parameters={"sample_limit": 7},
            config_sha256="0" * 64,
            idempotency_key=uuid4().hex.ljust(64, "0"),
            trace_id=str(uuid4()),
            status="approved",
            approved_by="demo-operator",
            approved_at=now,
            created_at=now,
            expires_at=now + timedelta(minutes=15),
        )
        session.add(proposal)
        session.flush()
        from app.services.run_proposals import configuration_hash_for_proposal

        proposal.config_sha256 = configuration_hash_for_proposal(session, proposal)
        run = Run(
            proposal_id=proposal.id,
            project_id=self.project.id,
            dataset_version_id=self.dataset.id,
            trace_id=proposal.trace_id,
            pipeline_template=proposal.pipeline_template,
            parameters=proposal.parameters,
            config_sha256=proposal.config_sha256,
            status="queued",
            created_at=now,
        )
        session.add(run)
        session.flush()
        session.add(
            RunEvent(
                run_id=run.id,
                sequence=1,
                status="queued",
                occurred_at=now,
            )
        )
        session.commit()
        return run.id

    def test_worker_records_synthetic_success_and_skips_duplicate_delivery(self) -> None:
        from app.db.models import Run, RunEvent
        from app.services.runs import execute_smoke_run

        self.assertTrue(execute_smoke_run(self.session_factory, self.run_id))
        self.assertFalse(execute_smoke_run(self.session_factory, self.run_id))

        with self.session_factory() as session:
            run = session.get(Run, self.run_id)
            self.assertEqual(run.status, "succeeded")
            self.assertEqual(run.result["processed_count"], 7)
            self.assertTrue(run.result["synthetic_only"])
            self.assertFalse(run.result["research_ready"])
            self.assertIsNotNone(run.started_at)
            self.assertIsNotNone(run.finished_at)
            self.assertIsNone(run.error_code)
            events = list(
                session.query(RunEvent)
                .filter_by(run_id=self.run_id)
                .order_by(RunEvent.sequence)
            )
            self.assertEqual([event.status for event in events], ["queued", "running", "succeeded"])
            self.assertEqual([event.sequence for event in events], [1, 2, 3])
            self.assertEqual([event.error_code for event in events], [None, None, None])

    def test_worker_limits_match_the_versioned_template_manifest(self) -> None:
        from app.services.template_registry import load_template_manifest
        from app.worker import celery_app

        limits = load_template_manifest("research-smoke-v1").manifest.resource_limits

        self.assertEqual(celery_app.conf.worker_concurrency, limits.max_concurrent_runs)
        self.assertEqual(celery_app.conf.task_soft_time_limit, limits.soft_timeout_seconds)
        self.assertEqual(celery_app.conf.task_time_limit, limits.hard_timeout_seconds)

    def test_worker_rejects_a_queued_run_when_its_template_manifest_changes(self) -> None:
        from app.db.models import Run, RunEvent
        from app.services.runs import execute_smoke_run

        manifest_path = BACKEND_DIR / "app" / "data" / "templates" / "research-smoke-v1.json"
        manifest_bytes = manifest_path.read_bytes()
        with tempfile.TemporaryDirectory() as temp_dir:
            temporary_manifest = Path(temp_dir) / manifest_path.name
            temporary_manifest.write_bytes(manifest_bytes)
            changed_manifest = json.loads(manifest_bytes)
            changed_manifest["version"] = "1.0.1"
            temporary_manifest.write_text(
                json.dumps(changed_manifest, ensure_ascii=True, sort_keys=True),
                encoding="utf-8",
            )
            with patch("app.services.template_registry.TEMPLATE_MANIFEST_DIR", Path(temp_dir)):
                self.assertFalse(execute_smoke_run(self.session_factory, self.run_id))

        with self.session_factory() as session:
            run = session.get(Run, self.run_id)
            self.assertEqual(run.status, "failed")
            self.assertEqual(run.error_code, "WORKER_EXECUTION_FAILED")
            events = list(
                session.query(RunEvent)
                .filter_by(run_id=self.run_id)
                .order_by(RunEvent.sequence)
            )
            self.assertEqual([event.status for event in events], ["queued", "running", "failed"])

    def test_worker_parameter_validation_uses_strict_manifest_types(self) -> None:
        from app.services.runs import calculate_smoke_result

        with self.assertRaises(ValueError):
            calculate_smoke_result({"sample_limit": True})

    def test_worker_records_only_a_stable_error_code_on_failure(self) -> None:
        from app.db.models import Run, RunEvent
        from app.services import runs

        with patch.object(runs, "calculate_smoke_result", side_effect=RuntimeError("private payload")):
            self.assertFalse(runs.execute_smoke_run(self.session_factory, self.run_id))

        with self.session_factory() as session:
            run = session.get(Run, self.run_id)
            self.assertEqual(run.status, "failed")
            self.assertEqual(run.error_code, "WORKER_EXECUTION_FAILED")
            self.assertIsNone(run.result)
            events = list(
                session.query(RunEvent)
                .filter_by(run_id=self.run_id)
                .order_by(RunEvent.sequence)
            )
            self.assertEqual([event.status for event in events], ["queued", "running", "failed"])
            self.assertEqual(events[-1].error_code, "WORKER_EXECUTION_FAILED")


if __name__ == "__main__":
    unittest.main()
