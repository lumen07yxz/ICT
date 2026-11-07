"""Run proposal API tests cover pending-only creation and member-scoped reading."""

import asyncio
import hashlib
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class RunProposalApiTests(unittest.TestCase):
    def setUp(self) -> None:
        from app.db.models import Base
        from app.db.seed_demo import seed_demo_project
        from app.main import create_app

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        with self.session_factory() as session:
            self.project = seed_demo_project(session)
            self.project_id = str(self.project.id)
        self.internal_key = "internal-only-test-key"
        self.app = create_app(
            session_factory=self.session_factory,
            auth_tokens={"operator": "operator-token", "viewer": "viewer-token"},
            internal_api_key=self.internal_key,
        )

    def tearDown(self) -> None:
        self.engine.dispose()

    def request(self, method: str, path: str, *, token: str | None = None, **kwargs) -> httpx.Response:
        async def send() -> httpx.Response:
            headers = dict(kwargs.pop("headers", {}))
            if token:
                headers["Authorization"] = f"Bearer {token}"
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, path, headers=headers, **kwargs)

        return asyncio.run(send())

    @staticmethod
    def proposal_payload(**changes: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "project_id": "demo-research",
            "dataset_version": "dataset-synthetic-v1",
            "pipeline_template": "research-smoke-v1",
            "sample_limit": 7,
        }
        payload.update(changes)
        return payload

    def create_internal(self, key: str = "0" * 64, **changes: object) -> httpx.Response:
        return self.request(
            "POST",
            "/internal/v1/run-proposals",
            headers={"X-ICT-Internal-Key": self.internal_key, "Idempotency-Key": key},
            json=self.proposal_payload(**changes),
        )

    def test_internal_create_adds_only_a_pending_proposal_with_fixed_configuration(self) -> None:
        response = self.create_internal()

        self.assertEqual(response.status_code, 201, response.text)
        proposal = response.json()
        self.assertEqual(proposal["status"], "pending_approval")
        self.assertEqual(proposal["pipeline_template"], "research-smoke-v1")
        self.assertEqual(proposal["dataset_version"], "dataset-synthetic-v1")
        self.assertEqual(proposal["parameters"], {"sample_limit": 7})
        self.assertEqual(len(proposal["config_sha256"]), 64)
        self.assertIsNone(proposal["run_id"])
        self.assertNotIn("storage_key", response.text)

        from app.db.models import RunProposal

        with self.session_factory() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(RunProposal)), 1)
            from app.db.models import Run

            self.assertEqual(session.scalar(select(func.count()).select_from(Run)), 0)
            stored = session.scalar(select(RunProposal))
            self.assertEqual(stored.status, "pending_approval")
            self.assertGreater(stored.expires_at, stored.created_at)
            self.assertLessEqual(stored.expires_at - stored.created_at, timedelta(minutes=15, seconds=1))

    def test_configuration_hash_pins_the_versioned_template_manifest(self) -> None:
        response = self.create_internal()
        self.assertEqual(response.status_code, 201, response.text)

        manifest_path = BACKEND_DIR / "app" / "data" / "templates" / "research-smoke-v1.json"
        self.assertTrue(manifest_path.is_file(), "the fixed template must have a versioned manifest")
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)

        from app.db.models import RunProposal

        with self.session_factory() as session:
            proposal = session.scalar(select(RunProposal))
            expected_payload = {
                "project_id": str(proposal.project_id),
                "dataset_version_id": str(proposal.dataset_version_id),
                "pipeline_template": proposal.pipeline_template,
                "template_version": manifest["version"],
                "template_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                "parameters": {"sample_limit": 7},
            }
        canonical = json.dumps(
            expected_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        expected_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.assertEqual(response.json()["config_sha256"], expected_hash)

    def test_changed_template_manifest_blocks_approval_without_creating_a_run(self) -> None:
        manifest_path = BACKEND_DIR / "app" / "data" / "templates" / "research-smoke-v1.json"
        manifest_bytes = manifest_path.read_bytes()

        with tempfile.TemporaryDirectory() as temp_dir:
            temporary_manifest = Path(temp_dir) / manifest_path.name
            temporary_manifest.write_bytes(manifest_bytes)
            with patch("app.services.template_registry.TEMPLATE_MANIFEST_DIR", Path(temp_dir)):
                created = self.create_internal(key="9" * 64)
                proposal_id = created.json()["id"]
                changed_manifest = json.loads(manifest_bytes)
                changed_manifest["version"] = "1.0.1"
                temporary_manifest.write_text(
                    json.dumps(changed_manifest, ensure_ascii=True, sort_keys=True),
                    encoding="utf-8",
                )
                approval = self.request(
                    "POST",
                    f"/api/v1/run-proposals/{proposal_id}/approve",
                    token="operator-token",
                )

        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(approval.status_code, 409, approval.text)
        self.assertEqual(approval.json()["error"]["code"], "PROPOSAL_CONFIG_MISMATCH")
        from app.db.models import Run, RunProposal

        with self.session_factory() as session:
            proposal = session.scalar(select(RunProposal))
            self.assertEqual(proposal.status, "pending_approval")
            self.assertEqual(session.scalar(select(func.count()).select_from(Run)), 0)

    def test_proposal_creation_fails_closed_when_template_manifest_is_missing(self) -> None:
        from app.db.models import RunProposal

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("app.services.template_registry.TEMPLATE_MANIFEST_DIR", Path(temp_dir)):
                response = self.create_internal(key="8" * 64)

        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["error"]["code"], "TEMPLATE_REGISTRY_UNAVAILABLE")
        with self.session_factory() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(RunProposal)), 0)

    def test_member_can_read_only_the_fixed_template_contract(self) -> None:
        path = f"/api/v1/projects/{self.project_id}/templates/research-smoke-v1"
        unauthenticated = self.request("GET", path)
        response = self.request("GET", path, token="viewer-token")
        unknown = self.request(
            "GET",
            f"/api/v1/projects/{self.project_id}/templates/unknown-v1",
            token="viewer-token",
        )

        self.assertEqual(unauthenticated.status_code, 401)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(unknown.status_code, 404)
        manifest_path = BACKEND_DIR / "app" / "data" / "templates" / "research-smoke-v1.json"
        manifest_bytes = manifest_path.read_bytes()
        body = response.json()
        self.assertEqual(
            set(body),
            {
                "template_id",
                "version",
                "manifest_sha256",
                "executor",
                "dataset_version",
                "permission_scope",
                "resource_limits",
                "inputs",
                "parameters",
                "outputs",
                "states",
                "error_codes",
            },
        )
        self.assertEqual(body["template_id"], "research-smoke-v1")
        self.assertEqual(body["manifest_sha256"], hashlib.sha256(manifest_bytes).hexdigest())
        self.assertEqual(body["parameters"]["sample_limit"]["minimum"], 1)
        self.assertEqual(body["parameters"]["sample_limit"]["maximum"], 100)
        self.assertFalse(body["outputs"]["research_ready"]["const"])
        self.assertNotIn("path", body)

    def test_template_contract_requires_project_membership(self) -> None:
        from app.db.models import Project, Workspace

        private_project_id = uuid4()
        with self.session_factory() as session:
            session.add(
                Project(
                    id=private_project_id,
                    workspace=Workspace(id=uuid4(), name="Private workspace", created_by="test"),
                    name="Private",
                    domain="general",
                )
            )
            session.commit()

        response = self.request(
            "GET",
            f"/api/v1/projects/{private_project_id}/templates/research-smoke-v1",
            token="viewer-token",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "PROJECT_NOT_FOUND")

    def test_template_contract_reports_a_safe_error_when_manifest_is_missing(self) -> None:
        from app.services.template_registry import TemplateRegistryError

        with patch(
            "app.api.v1.projects.load_template_manifest",
            side_effect=TemplateRegistryError("private filesystem path"),
        ):
            response = self.request(
                "GET",
                f"/api/v1/projects/{self.project_id}/templates/research-smoke-v1",
                token="viewer-token",
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "TEMPLATE_REGISTRY_UNAVAILABLE")
        self.assertNotIn("private filesystem path", response.text)

    def test_internal_create_is_idempotent_and_rejects_key_reuse_with_changed_configuration(self) -> None:
        key = "a" * 64
        first = self.create_internal(key=key)
        replay = self.create_internal(key=key)
        conflict = self.create_internal(key=key, sample_limit=8)

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(first.json()["id"], replay.json()["id"])
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()["error"]["code"], "IDEMPOTENCY_CONFLICT")

        from app.db.models import RunProposal

        with self.session_factory() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(RunProposal)), 1)

    def test_internal_route_requires_a_separate_configured_service_key(self) -> None:
        wrong = self.request(
            "POST",
            "/internal/v1/run-proposals",
            headers={
                "X-ICT-Internal-Key": "agentarts-public-key",
                "Idempotency-Key": "b" * 64,
            },
            json=self.proposal_payload(),
        )
        unconfigured = self.app_with_internal_key(None)

        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.json()["error"]["code"], "INTERNAL_UNAUTHORIZED")
        self.assertNotIn("agentarts-public-key", wrong.text)
        self.assertEqual(unconfigured.status_code, 503)
        self.assertEqual(unconfigured.json()["error"]["code"], "INTERNAL_AUTH_NOT_CONFIGURED")

    def app_with_internal_key(self, key: str | None) -> httpx.Response:
        from app.main import create_app

        app = create_app(
            session_factory=self.session_factory,
            auth_tokens={"operator": "operator-token", "viewer": "viewer-token"},
            internal_api_key=key,
        )

        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.post(
                    "/internal/v1/run-proposals",
                    headers={"Idempotency-Key": "c" * 64},
                    json=self.proposal_payload(),
                )

        return asyncio.run(send())

    def test_fixed_schema_rejects_unapproved_ids_extra_fields_and_invalid_sample_limits(self) -> None:
        unknown_project = self.create_internal(key="d" * 64, project_id="private-project")
        extra = self.create_internal(key="e" * 64, extra_field="must be rejected")
        invalid_limit = self.create_internal(key="f" * 64, sample_limit=1000)

        for response in (unknown_project, extra, invalid_limit):
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST")

    def test_team_api_lists_only_proposals_in_projects_visible_to_the_identity(self) -> None:
        self.create_internal(key="1" * 64)
        from app.db.models import DatasetVersion, Membership, Project, RunProposal, Workspace

        private_project_id = uuid4()
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            session.add(
                Project(
                    id=private_project_id,
                    workspace=Workspace(id=uuid4(), name="Private workspace", created_by="test"),
                    name="Private",
                    domain="general",
                )
            )
            session.add(Membership(project_id=private_project_id, user_id="demo-operator", role="operator"))
            dataset_id = uuid4()
            session.add(
                DatasetVersion(
                    id=dataset_id,
                    project_id=private_project_id,
                    version="synthetic-private-v1",
                    manifest_ref="synthetic://private/manifest",
                    schema_ref="synthetic://private/schema",
                    source="synthetic",
                    license_status="not_applicable",
                    split_policy={"type": "synthetic"},
                    created_by="demo-operator",
                )
            )
            session.add(
                RunProposal(
                    id=uuid4(),
                    project_id=private_project_id,
                    dataset_version_id=dataset_id,
                    created_by="agentarts-mcp",
                    pipeline_template="research-smoke-v1",
                    parameters={"sample_limit": 1},
                    config_sha256="a" * 64,
                    idempotency_key="2" * 64,
                    status="pending_approval",
                    created_at=now,
                    expires_at=now + timedelta(minutes=15),
                )
            )
            session.commit()

        viewer = self.request("GET", "/api/v1/run-proposals", token="viewer-token")
        operator = self.request("GET", "/api/v1/run-proposals", token="operator-token")

        self.assertEqual(viewer.status_code, 200, viewer.text)
        self.assertEqual(operator.status_code, 200, operator.text)
        self.assertEqual(len(viewer.json()), 1)
        self.assertEqual(len(operator.json()), 2)
        self.assertTrue(all("storage_key" not in item for item in operator.json()))

    def test_team_proposal_read_requires_authentication_and_database(self) -> None:
        unauthenticated = self.request("GET", "/api/v1/run-proposals")
        self.assertEqual(unauthenticated.status_code, 401)

        from app.main import create_app

        app = create_app(
            auth_tokens={"operator": "operator-token", "viewer": "viewer-token"},
            internal_api_key=self.internal_key,
        )

        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                read_response = await client.get(
                    "/api/v1/run-proposals",
                    headers={"Authorization": "Bearer operator-token"},
                )
                create_response = await client.post(
                    "/internal/v1/run-proposals",
                    headers={
                        "X-ICT-Internal-Key": self.internal_key,
                        "Idempotency-Key": "4" * 64,
                    },
                    json=self.proposal_payload(),
                )
                return read_response, create_response

        read_unavailable, create_unavailable = asyncio.run(send())
        for unavailable in (read_unavailable, create_unavailable):
            self.assertEqual(unavailable.status_code, 503)
            self.assertEqual(unavailable.json()["error"]["code"], "DATABASE_NOT_CONFIGURED")

    def test_expired_status_is_derived_during_read_without_changing_the_stored_state(self) -> None:
        self.create_internal(key="3" * 64)
        from app.db.models import RunProposal

        with self.session_factory() as session:
            proposal = session.scalar(select(RunProposal))
            proposal.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            session.commit()

        response = self.request("GET", "/api/v1/run-proposals", token="viewer-token")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()[0]["status"], "expired")
        with self.session_factory() as session:
            stored = session.scalar(select(RunProposal))
            self.assertEqual(stored.status, "pending_approval")

    def test_only_project_operator_can_approve_and_approval_is_idempotent(self) -> None:
        self.create_internal(key="5" * 64)
        self.app.state.run_dispatcher = lambda run_id: self.dispatched.append(run_id)
        self.dispatched = []
        proposal_id = self.request("GET", "/api/v1/run-proposals", token="operator-token").json()[0]["id"]

        viewer = self.request(
            "POST", f"/api/v1/run-proposals/{proposal_id}/approve", token="viewer-token"
        )
        self.assertEqual(viewer.status_code, 403)
        self.assertEqual(viewer.json()["error"]["code"], "FORBIDDEN")

        with self.session_factory() as session:
            from app.db.models import Run

            self.assertEqual(session.scalar(select(func.count()).select_from(Run)), 0)

        approved = self.request(
            "POST", f"/api/v1/run-proposals/{proposal_id}/approve", token="operator-token"
        )
        replay = self.request(
            "POST", f"/api/v1/run-proposals/{proposal_id}/approve", token="operator-token"
        )
        self.assertEqual(approved.status_code, 201, approved.text)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(approved.json()["status"], "queued")
        self.assertEqual(approved.json()["id"], replay.json()["id"])
        self.assertEqual(approved.json()["quality_status"], "success")
        self.assertEqual(approved.json()["quality_rule_set_version"], "generic-manifest-v1")
        self.assertEqual(len(approved.json()["quality_report_sha256"]), 64)
        self.assertTrue(approved.json()["trace_id"])
        self.assertEqual([str(item) for item in self.dispatched], [approved.json()["id"]])

        visible_runs = self.request("GET", "/api/v1/runs", token="viewer-token")
        self.assertEqual(visible_runs.status_code, 200, visible_runs.text)
        self.assertEqual(len(visible_runs.json()), 1)
        self.assertEqual(visible_runs.json()[0]["proposal_id"], proposal_id)
        self.assertEqual(visible_runs.json()[0]["trace_id"], approved.json()["trace_id"])
        events = self.request(
            "GET", f"/api/v1/runs/{approved.json()['id']}/events", token="viewer-token"
        )
        self.assertEqual(events.status_code, 200, events.text)
        self.assertEqual(
            [(event["sequence"], event["status"]) for event in events.json()],
            [(1, "queued")],
        )
        self.assertEqual(
            self.request("GET", f"/api/v1/runs/{approved.json()['id']}", token="viewer-token").status_code,
            200,
        )

        with self.session_factory() as session:
            from app.db.models import Run, RunProposal

            self.assertEqual(session.scalar(select(func.count()).select_from(Run)), 1)
            proposal = session.scalar(
                select(RunProposal).where(RunProposal.idempotency_key == "5" * 64)
            )
            run = session.scalar(select(Run).where(Run.proposal_id == proposal.id))
            self.assertEqual(proposal.status, "approved")
            self.assertEqual(proposal.approved_by, "demo-operator")
            self.assertIsNotNone(proposal.approved_at)
            self.assertEqual(run.quality_status, "success")
            self.assertEqual(run.quality_rule_set_version, "generic-manifest-v1")
            self.assertEqual(run.quality_report_sha256, approved.json()["quality_report_sha256"])

    def test_run_events_hide_runs_outside_the_callers_membership(self) -> None:
        from app.db.models import Membership

        self.create_internal(key="b" * 64)
        self.app.state.run_dispatcher = lambda _run_id: None
        proposal_id = self.request("GET", "/api/v1/run-proposals", token="operator-token").json()[0]["id"]
        approved = self.request(
            "POST", f"/api/v1/run-proposals/{proposal_id}/approve", token="operator-token"
        )
        self.assertEqual(approved.status_code, 201, approved.text)
        with self.session_factory() as session:
            membership = session.get(Membership, (self.project.id, "demo-viewer"))
            session.delete(membership)
            session.commit()

        response = self.request(
            "GET", f"/api/v1/runs/{approved.json()['id']}/events", token="viewer-token"
        )
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["error"]["code"], "RUN_NOT_FOUND")

    def test_quality_report_is_member_scoped_and_never_contains_manifest_values(self) -> None:
        path = "/api/v1/projects/demo/demo-research/datasets/dataset-synthetic-v1/quality-report"
        response = self.request("GET", path, token="viewer-token")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["dataset_version"], "dataset-synthetic-v1")
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["rule_set_version"], "generic-manifest-v1")
        self.assertTrue(payload["synthetic_only"])
        self.assertFalse(payload["research_ready"])
        self.assertNotIn("demo-record", response.text)
        self.assertEqual(self.request("GET", path).status_code, 401)

    def test_blocker_report_prevents_approval_and_worker_dispatch(self) -> None:
        self.create_internal(key="a" * 64)
        proposal_id = self.request("GET", "/api/v1/run-proposals", token="operator-token").json()[0]["id"]
        from app.db.models import Run, RunProposal
        from app.services.dataset_quality import inspect_manifest_bytes

        blocker_report = inspect_manifest_bytes(
            b"record_id,group_id,split,label\n"
            b"r-1,g-1,train,a\n"
            b"r-1,g-1,test,a\n"
        )
        dispatched: list[object] = []
        self.app.state.run_dispatcher = lambda run_id: dispatched.append(run_id)
        with patch("app.services.runs.inspect_dataset_manifest", return_value=blocker_report):
            response = self.request(
                "POST", f"/api/v1/run-proposals/{proposal_id}/approve", token="operator-token"
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "DATA_QUALITY_BLOCKED")
        self.assertEqual(dispatched, [])
        with self.session_factory() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Run)), 0)
            proposal = session.get(RunProposal, UUID(proposal_id))
            self.assertEqual(proposal.status, "pending_approval")

    def test_expired_or_hash_changed_proposals_never_create_runs(self) -> None:
        self.create_internal(key="6" * 64)
        self.create_internal(key="7" * 64)
        from app.db.models import RunProposal

        with self.session_factory() as session:
            proposals = {
                item.idempotency_key: item
                for item in session.scalars(select(RunProposal))
            }
            proposals["6" * 64].expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            proposals["7" * 64].config_sha256 = "f" * 64
            expired_id = str(proposals["6" * 64].id)
            changed_id = str(proposals["7" * 64].id)
            session.commit()

        expired = self.request(
            "POST", f"/api/v1/run-proposals/{expired_id}/approve", token="operator-token"
        )
        changed = self.request(
            "POST", f"/api/v1/run-proposals/{changed_id}/approve", token="operator-token"
        )
        self.assertEqual(expired.status_code, 409)
        self.assertEqual(expired.json()["error"]["code"], "PROPOSAL_EXPIRED")
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(changed.json()["error"]["code"], "PROPOSAL_CONFIG_MISMATCH")
        with self.session_factory() as session:
            from app.db.models import Run

            self.assertEqual(session.scalar(select(func.count()).select_from(Run)), 0)

    def test_queue_failure_is_recorded_as_a_safe_failed_run(self) -> None:
        self.create_internal(key="8" * 64)
        proposal_id = self.request("GET", "/api/v1/run-proposals", token="operator-token").json()[0]["id"]

        def fail_dispatch(_run_id: str) -> None:
            raise OSError("redis credentials must not be returned")

        self.app.state.run_dispatcher = fail_dispatch
        response = self.request(
            "POST", f"/api/v1/run-proposals/{proposal_id}/approve", token="operator-token"
        )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["status"], "failed")
        self.assertEqual(response.json()["error_code"], "QUEUE_UNAVAILABLE")
        self.assertNotIn("redis credentials", response.text)
        events = self.request(
            "GET", f"/api/v1/runs/{response.json()['id']}/events", token="viewer-token"
        )
        self.assertEqual(events.status_code, 200, events.text)
        self.assertEqual(
            [(event["sequence"], event["status"], event["error_code"]) for event in events.json()],
            [(1, "queued", None), (3, "failed", "QUEUE_UNAVAILABLE")],
        )

    def test_operator_token_without_project_operator_membership_cannot_approve(self) -> None:
        self.create_internal(key="9" * 64)
        from app.db.models import Membership, Run

        with self.session_factory() as session:
            membership = session.get(Membership, (self.project.id, "demo-operator"))
            membership.role = "viewer"
            session.commit()
        proposal_id = self.request(
            "GET", "/api/v1/run-proposals", token="operator-token"
        ).json()[0]["id"]

        response = self.request(
            "POST", f"/api/v1/run-proposals/{proposal_id}/approve", token="operator-token"
        )
        self.assertEqual(response.status_code, 403)
        with self.session_factory() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Run)), 0)


if __name__ == "__main__":
    unittest.main()
