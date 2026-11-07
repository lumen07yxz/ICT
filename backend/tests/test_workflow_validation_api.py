"""Workflow validation responses expose actionable component contract issues."""

import asyncio
import sys
import unittest
from pathlib import Path

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class WorkflowValidationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        from app.db.models import Base
        from app.main import create_app

        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
        self.app = create_app(
            session_factory=self.session_factory,
            auth_tokens={"operator": "operator-test-token", "viewer": "viewer-test-token"},
        )

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_max_length_validation_has_actionable_details_in_workflow_api(self) -> None:
        async def validate_overlong_doi() -> dict[str, object]:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app),
                base_url="http://testserver",
                headers={"Authorization": "Bearer operator-test-token"},
            ) as client:
                project = await client.post(
                    "/api/v1/projects",
                    json={"name": "Schema validation", "domain": "general", "description": "synthetic"},
                )
                self.assertEqual(project.status_code, 201, project.text)
                project_id = project.json()["id"]
                created = await client.post(
                    f"/api/v1/projects/{project_id}/workflows",
                    json={"name": "Length contract", "description": ""},
                )
                self.assertEqual(created.status_code, 201, created.text)
                workflow_id = created.json()["id"]
                graph = {
                    "schema_version": "ict.workflow.v1",
                    "nodes": [
                        {
                            "id": "doi",
                            "type": "research",
                            "position": {"x": 0, "y": 0},
                            "data": {
                                "component_id": "ict.paper.crossref_metadata",
                                "component_version": "1.0.0",
                                "parameters": {"doi": "x" * 301},
                            },
                        }
                    ],
                    "edges": [],
                }
                saved = await client.patch(
                    f"/api/v1/workflows/{workflow_id}",
                    json={
                        "revision": 1,
                        "name": "Length contract",
                        "description": "",
                        "graph": graph,
                    },
                )
                self.assertEqual(saved.status_code, 200, saved.text)
                response = await client.post(f"/api/v1/workflows/{workflow_id}/validations")
                self.assertEqual(response.status_code, 200, response.text)
                return response.json()

        payload = asyncio.run(validate_overlong_doi())
        issue = next(
            item for item in payload["issues"]
            if item["code"] == "PARAMETER_MAX_LENGTH_EXCEEDED"
        )

        self.assertEqual(payload["contract_status"], "invalid")
        self.assertEqual(issue["title"], "参数超过允许长度")
        self.assertIn("300", issue["reason"])
        self.assertIn("最大长度限制", issue["guidance"])
        self.assertNotIn("x" * 301, str(payload))

    def test_min_length_validation_copy_is_actionable(self) -> None:
        from app.api.v1.workflows import _workflow_validation_issue_read

        issue = _workflow_validation_issue_read(
            {
                "scope": "component",
                "code": "PARAMETER_MIN_LENGTH_UNSATISFIED",
                "message": "参数“文本”长度不得少于 2 个字符。",
                "node_id": "text-node",
                "edge_id": None,
            }
        )

        self.assertEqual(issue.title, "参数短于最小长度")
        self.assertIn("最小长度限制", issue.guidance)


if __name__ == "__main__":
    unittest.main()
