"""Cold-start local projects and workflows stay available without platform APIs."""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

import httpx


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class LocalRuntimeProjectTests(unittest.TestCase):
    def test_local_project_and_workflow_persist_across_runtime_restart(self) -> None:
        from app.local_runtime import create_local_runtime_app

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin = "http://127.0.0.1:8766"

            async def create_project_and_workflow() -> tuple[str, str]:
                app = create_local_runtime_app(root=root)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url=origin,
                    headers={"Origin": origin},
                ) as client:
                    session = await client.post("/api/v1/local/session")
                    self.assertEqual(session.status_code, 200)
                    auth = {"X-ICT-Local-Token": session.json()["token"]}
                    created = await client.post(
                        "/api/v1/local/projects",
                        json={"name": "离线 CSV 质检", "domain": "数据分析", "description": "本机预检工作区"},
                        headers=auth,
                    )
                    self.assertEqual(created.status_code, 201, created.text)
                    project = created.json()
                    self.assertEqual(project["sync_state"], "local_only")
                    self.assertEqual(project["workflow_count"], 0)

                    workflow_response = await client.post(
                        f"/api/v1/local/projects/{project['id']}/workflows",
                        json={"name": "清单结构预检", "description": "本机 CSV 工作流"},
                        headers=auth,
                    )
                    self.assertEqual(workflow_response.status_code, 201, workflow_response.text)
                    workflow = workflow_response.json()
                    self.assertEqual(workflow["project_id"], project["id"])
                    self.assertEqual(workflow["revision"], 1)
                    self.assertEqual(workflow["graph"], {"schema_version": "ict.workflow.v1", "nodes": [], "edges": []})
                    return project["id"], workflow["id"]

            project_id, workflow_id = asyncio.run(create_project_and_workflow())

            async def reopen_and_read() -> None:
                app = create_local_runtime_app(root=root)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url=origin,
                    headers={"Origin": origin},
                ) as client:
                    session = await client.post("/api/v1/local/session")
                    auth = {"X-ICT-Local-Token": session.json()["token"]}
                    projects = await client.get("/api/v1/local/projects", headers=auth)
                    self.assertEqual(projects.status_code, 200)
                    self.assertEqual([item["id"] for item in projects.json()], [project_id])
                    detail = await client.get(f"/api/v1/local/projects/{project_id}", headers=auth)
                    self.assertEqual(detail.status_code, 200)
                    workflows = await client.get(f"/api/v1/local/projects/{project_id}/workflows", headers=auth)
                    self.assertEqual(workflows.status_code, 200)
                    self.assertEqual([item["id"] for item in workflows.json()], [workflow_id])
                    workflow = await client.get(f"/api/v1/local/workflows/{workflow_id}", headers=auth)
                    self.assertEqual(workflow.status_code, 200)
                    self.assertEqual(workflow.json()["name"], "清单结构预检")
                    self.assertEqual(workflow.json()["revision"], 1)

            asyncio.run(reopen_and_read())

    def test_local_catalog_rejects_invalid_input_and_unknown_project(self) -> None:
        from app.local_runtime import create_local_runtime_app

        with tempfile.TemporaryDirectory() as directory:
            app = create_local_runtime_app(root=Path(directory))

            async def exercise() -> None:
                origin = "http://127.0.0.1:8766"
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url=origin,
                    headers={"Origin": origin},
                ) as client:
                    session = await client.post("/api/v1/local/session")
                    auth = {"X-ICT-Local-Token": session.json()["token"]}
                    invalid = await client.post(
                        "/api/v1/local/projects",
                        json={"name": "   ", "domain": "数据分析", "description": ""},
                        headers=auth,
                    )
                    self.assertEqual(invalid.status_code, 422)
                    unknown = await client.post(
                        "/api/v1/local/projects/missing-project/workflows",
                        json={"name": "清单结构预检", "description": ""},
                        headers=auth,
                    )
                    self.assertEqual(unknown.status_code, 404)

            asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
