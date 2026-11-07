"""W2 project access API tests use only a temporary synthetic SQLite database."""

import asyncio
import sys
import unittest
from pathlib import Path

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class ProjectApiTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from app.db.models import Base
            from app.db.seed_demo import seed_demo_project
            from app.main import create_app
        except ModuleNotFoundError as exc:
            self.fail(f"W2 project access is not implemented yet: {exc}")

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        with self.session_factory() as session:
            project = seed_demo_project(session)
            self.project_id = str(project.id)

        self.app = create_app(
            session_factory=self.session_factory,
            auth_tokens={"operator": "operator-test-token", "viewer": "viewer-test-token"},
        )

    def tearDown(self) -> None:
        self.engine.dispose()

    def request(self, method: str, path: str, token: str | None = None, **kwargs) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app)
            headers = kwargs.pop("headers", {})
            if token:
                headers["Authorization"] = f"Bearer {token}"
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, path, headers=headers, **kwargs)

        return asyncio.run(send())

    def test_viewer_can_read_seed_project_and_synthetic_dataset_manifest(self) -> None:
        response = self.request("GET", f"/api/v1/projects/{self.project_id}", "viewer-test-token")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["role"], "viewer")
        self.assertEqual(payload["datasets"][0]["source"], "synthetic")
        self.assertEqual(payload["datasets"][0]["license_status"], "not_applicable")
        self.assertFalse(payload["datasets"][0]["research_ready"])
        self.assertNotIn("storage_key", response.text)

    def test_project_list_is_scoped_to_membership_and_returns_the_callers_role(self) -> None:
        viewer = self.request("GET", "/api/v1/projects", "viewer-test-token")
        operator = self.request("GET", "/api/v1/projects", "operator-test-token")

        self.assertEqual(viewer.status_code, 200)
        self.assertEqual(operator.status_code, 200)
        self.assertEqual(len(viewer.json()), 1)
        self.assertEqual(viewer.json()[0]["id"], self.project_id)
        self.assertEqual(viewer.json()[0]["role"], "viewer")
        self.assertEqual(operator.json()[0]["role"], "operator")

    def test_missing_or_invalid_bearer_token_is_rejected_without_echo(self) -> None:
        missing = self.request("GET", "/api/v1/projects")
        invalid = self.request("GET", "/api/v1/projects", "not-a-valid-token")

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(invalid.json()["error"]["code"], "UNAUTHORIZED")
        self.assertNotIn("not-a-valid-token", invalid.text)

    def test_viewer_cannot_create_a_project(self) -> None:
        response = self.request(
            "POST",
            "/api/v1/projects",
            "viewer-test-token",
            json={"name": "Blocked project", "domain": "general", "description": ""},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "OPERATOR_REQUIRED")

    def test_operator_can_create_a_project_but_viewer_cannot_discover_it(self) -> None:
        created = self.request(
            "POST",
            "/api/v1/projects",
            "operator-test-token",
            json={"name": "New demo", "domain": "general", "description": "Synthetic only"},
        )

        self.assertEqual(created.status_code, 201)
        new_project_id = created.json()["id"]
        self.assertEqual(created.json()["role"], "operator")

        hidden = self.request("GET", f"/api/v1/projects/{new_project_id}", "viewer-test-token")
        missing = self.request("GET", f"/api/v1/projects/{'0' * 32}", "viewer-test-token")
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(hidden.json()["error"]["code"], "PROJECT_NOT_FOUND")
        self.assertEqual(hidden.json()["error"]["code"], missing.json()["error"]["code"])

    def test_authentication_fails_closed_when_demo_tokens_are_not_configured(self) -> None:
        from app.main import create_app

        unconfigured_app = create_app(session_factory=self.session_factory, auth_tokens={})
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=unconfigured_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.get("/api/v1/projects")

        response = asyncio.run(send())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "AUTH_NOT_CONFIGURED")


if __name__ == "__main__":
    unittest.main()
