"""Durable, user-controlled sync state for offline project copies."""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

import httpx


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class LocalProjectSyncOutboxTests(unittest.TestCase):
    def test_outbox_mappings_survive_runtime_restart_and_pending_sync_is_exclusive(self) -> None:
        from app.local_runtime import create_local_runtime_app

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin = "http://127.0.0.1:18791"

            async def create_and_sync() -> tuple[str, str]:
                app = create_local_runtime_app(root=root)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url=origin,
                    headers={"Origin": origin},
                ) as client:
                    session = await client.post("/api/v1/local/session")
                    self.assertEqual(session.status_code, 200, session.text)
                    auth = {"X-ICT-Local-Token": session.json()["token"]}
                    project_response = await client.post(
                        "/api/v1/local/projects",
                        json={"name": "离线同步项目", "domain": "数据分析", "description": "本机副本"},
                        headers=auth,
                    )
                    self.assertEqual(project_response.status_code, 201, project_response.text)
                    project_id = project_response.json()["id"]
                    workflow_response = await client.post(
                        f"/api/v1/local/projects/{project_id}/workflows",
                        json={"name": "CSV 预检", "description": ""},
                        headers=auth,
                    )
                    self.assertEqual(workflow_response.status_code, 201, workflow_response.text)
                    workflow_id = workflow_response.json()["id"]

                    started = await client.post(
                        f"/api/v1/local/projects/{project_id}/sync-state/start",
                        json={"allow_pending_retry": False},
                        headers=auth,
                    )
                    self.assertEqual(started.status_code, 200, started.text)
                    self.assertEqual(started.json()["status"], "pending")

                    duplicate_start = await client.post(
                        f"/api/v1/local/projects/{project_id}/sync-state/start",
                        json={"allow_pending_retry": False},
                        headers=auth,
                    )
                    self.assertEqual(duplicate_start.status_code, 409, duplicate_start.text)
                    self.assertEqual(duplicate_start.json()["error"]["code"], "LOCAL_SYNC_ALREADY_RUNNING")

                    project_pending = await client.put(
                        f"/api/v1/local/projects/{project_id}/sync-state",
                        json={
                            "status": "pending",
                            "platform_project_id": "platform-project-1",
                            "error_code": None,
                        },
                        headers=auth,
                    )
                    self.assertEqual(project_pending.status_code, 200, project_pending.text)
                    workflow_synced = await client.put(
                        f"/api/v1/local/projects/{project_id}/workflows/{workflow_id}/sync-state",
                        json={
                            "status": "synced",
                            "platform_workflow_id": "platform-workflow-1",
                            "synced_revision": 2,
                            "source_revision": 1,
                            "error_code": None,
                        },
                        headers=auth,
                    )
                    self.assertEqual(workflow_synced.status_code, 200, workflow_synced.text)
                    project_synced = await client.put(
                        f"/api/v1/local/projects/{project_id}/sync-state",
                        json={
                            "status": "synced",
                            "platform_project_id": "platform-project-1",
                            "error_code": None,
                        },
                        headers=auth,
                    )
                    self.assertEqual(project_synced.status_code, 200, project_synced.text)
                    self.assertEqual(project_synced.json()["status"], "synced")
                    return project_id, workflow_id

            project_id, workflow_id = asyncio.run(create_and_sync())

            async def read_after_restart() -> None:
                restarted_app = create_local_runtime_app(root=root)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=restarted_app),
                    base_url=origin,
                    headers={"Origin": origin},
                ) as client:
                    session = await client.post("/api/v1/local/session")
                    auth = {"X-ICT-Local-Token": session.json()["token"]}
                    state = await client.get(
                        f"/api/v1/local/projects/{project_id}/sync-state",
                        headers=auth,
                    )
                    self.assertEqual(state.status_code, 200, state.text)
                    payload = state.json()
                    self.assertEqual(payload["status"], "synced")
                    self.assertEqual(payload["platform_project_id"], "platform-project-1")
                    self.assertEqual(payload["workflows"], [{
                        "workflow_id": workflow_id,
                        "status": "synced",
                        "platform_workflow_id": "platform-workflow-1",
                        "synced_revision": 2,
                        "source_revision": 1,
                        "error_code": None,
                        "updated_at": payload["workflows"][0]["updated_at"],
                    }])

            asyncio.run(read_after_restart())

    def test_editing_a_synced_workflow_marks_the_local_copy_pending(self) -> None:
        from app.local_runtime import create_local_runtime_app

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin = "http://127.0.0.1:18792"

            async def exercise() -> None:
                app = create_local_runtime_app(root=root)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url=origin,
                    headers={"Origin": origin},
                ) as client:
                    session = await client.post("/api/v1/local/session")
                    auth = {"X-ICT-Local-Token": session.json()["token"]}
                    project_response = await client.post(
                        "/api/v1/local/projects",
                        json={"name": "本机修订项目", "domain": "数据分析", "description": ""},
                        headers=auth,
                    )
                    self.assertEqual(project_response.status_code, 201, project_response.text)
                    project_id = project_response.json()["id"]
                    workflow_response = await client.post(
                        f"/api/v1/local/projects/{project_id}/workflows",
                        json={"name": "本机工作流", "description": ""},
                        headers=auth,
                    )
                    workflow_id = workflow_response.json()["id"]
                    await client.put(
                        f"/api/v1/local/projects/{project_id}/workflows/{workflow_id}/sync-state",
                        json={
                            "status": "synced",
                            "platform_workflow_id": "platform-workflow-2",
                            "synced_revision": 4,
                            "source_revision": 1,
                            "error_code": None,
                        },
                        headers=auth,
                    )
                    await client.put(
                        f"/api/v1/local/projects/{project_id}/sync-state",
                        json={"status": "synced", "platform_project_id": "platform-project-2", "error_code": None},
                        headers=auth,
                    )

                    saved = await client.put(
                        f"/api/v1/local/workflows/{workflow_id}/draft",
                        json={
                            "revision": 2,
                            "graph": {"schema_version": "ict.workflow.v1", "nodes": [], "edges": []},
                            "name": "本机工作流",
                            "description": "新增的本机说明",
                        },
                        headers=auth,
                    )
                    self.assertEqual(saved.status_code, 200, saved.text)
                    self.assertEqual(saved.json()["revision"], 2)

                    state = await client.get(
                        f"/api/v1/local/projects/{project_id}/sync-state",
                        headers=auth,
                    )
                    self.assertEqual(state.status_code, 200, state.text)
                    payload = state.json()
                    self.assertEqual(payload["status"], "partial")
                    self.assertEqual(payload["workflows"][0]["status"], "pending")
                    self.assertEqual(payload["workflows"][0]["source_revision"], 1)

            asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
