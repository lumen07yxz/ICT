"""Offline reproduction tasks reuse the local workflow engine and artifact trace."""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

import httpx


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class LocalRuntimeReproductionTests(unittest.TestCase):
    def test_task_owned_workflow_run_and_report_persist_after_runtime_restart(self) -> None:
        from app.local_runtime import create_local_runtime_app

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin = "http://127.0.0.1:8766"

            async def create_task_workflow_and_run() -> tuple[str, str, str, str]:
                app = create_local_runtime_app(root=root)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url=origin,
                    headers={"Origin": origin},
                ) as client:
                    session = await client.post("/api/v1/local/session")
                    self.assertEqual(session.status_code, 200)
                    auth = {"X-ICT-Local-Token": session.json()["token"]}

                    project_response = await client.post(
                        "/api/v1/local/projects",
                        json={"name": "本机复现工作区", "domain": "数据分析", "description": ""},
                        headers=auth,
                    )
                    self.assertEqual(project_response.status_code, 201, project_response.text)
                    project_id = project_response.json()["id"]

                    task_response = await client.post(
                        "/api/v1/local/reproductions",
                        json={
                            "title": "离线实验核验任务",
                            "kind": "experiment",
                            "source": "用户提供的本机实验材料",
                            "claim": "记录待核验的实验主张",
                            "baseline": {"reference_note": "待人工核对的基准记录"},
                            "criteria_version": "criteria-draft-1",
                            "linked_project_id": project_id,
                        },
                        headers=auth,
                    )
                    self.assertEqual(task_response.status_code, 201, task_response.text)
                    task = task_response.json()
                    task_id = task["id"]
                    self.assertEqual(task["status"], "preparation")
                    self.assertEqual(task["linked_project_id"], project_id)
                    self.assertEqual(task["sync_state"], "local_only")

                    workflow_response = await client.post(
                        f"/api/v1/local/reproductions/{task_id}/workflows",
                        json={"name": "本机结构检查", "description": "复用现有 CSV 本机执行器"},
                        headers=auth,
                    )
                    self.assertEqual(workflow_response.status_code, 201, workflow_response.text)
                    workflow = workflow_response.json()
                    workflow_id = workflow["id"]
                    self.assertEqual(workflow["owner_type"], "reproduction")
                    self.assertEqual(workflow["owner_id"], task_id)
                    self.assertIsNone(workflow["project_id"])
                    self.assertEqual(workflow["reproduction_task_id"], task_id)

                    upload = await client.post(
                        "/api/v1/local/artifacts",
                        content=b"record_id,group_id,split,label\nr1,g1,train,a\nr2,g2,test,b\n",
                        headers={
                            **auth,
                            "Content-Type": "application/octet-stream",
                            "X-Artifact-File-Name": "synthetic-checklist.csv",
                            "X-ICT-Local-Consent": "confirmed",
                        },
                    )
                    self.assertEqual(upload.status_code, 201, upload.text)
                    artifact_id = upload.json()["artifact_id"]
                    graph = {
                        "schema_version": "ict.workflow.v1",
                        "nodes": [
                            {
                                "id": "csv-preflight",
                                "type": "research",
                                "position": {"x": 120, "y": 80},
                                "data": {
                                    "component_id": "ict.data.csv_manifest_preflight",
                                    "component_version": "1.0.0",
                                    "parameters": {"artifact_id": artifact_id},
                                },
                            }
                        ],
                        "edges": [],
                    }
                    saved = await client.put(
                        f"/api/v1/local/workflows/{workflow_id}/draft",
                        json={"revision": 2, "graph": graph},
                        headers=auth,
                    )
                    self.assertEqual(saved.status_code, 200, saved.text)

                    submitted = await client.post(
                        f"/api/v1/local/workflows/{workflow_id}/runs",
                        json={"target_node_ids": ["csv-preflight"]},
                        headers=auth,
                    )
                    self.assertEqual(submitted.status_code, 202, submitted.text)
                    run_id = submitted.json()["run_id"]
                    for _ in range(100):
                        run_response = await client.get(f"/api/v1/local/runs/{run_id}", headers=auth)
                        self.assertEqual(run_response.status_code, 200, run_response.text)
                        run = run_response.json()
                        if run["status"] in {"succeeded", "partially_succeeded", "failed", "cancelled"}:
                            break
                        await asyncio.sleep(0.01)
                    else:
                        self.fail("local reproduction workflow did not reach a terminal state")

                    self.assertEqual(run["status"], "succeeded")
                    self.assertEqual(run["node_runs"][0]["status"], "SUCCEEDED")
                    report_id = run["node_runs"][0]["output"]["quality_report"]["artifact_id"]
                    report_response = await client.get(
                        f"/api/v1/local/artifacts/{report_id}/csv-preflight-report",
                        headers=auth,
                    )
                    self.assertEqual(report_response.status_code, 200, report_response.text)
                    self.assertFalse(report_response.json()["research_result"])
                    return task_id, workflow_id, run_id, report_id

            task_id, workflow_id, run_id, report_id = asyncio.run(create_task_workflow_and_run())

            async def reopen_and_read() -> None:
                app = create_local_runtime_app(root=root)
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url=origin,
                    headers={"Origin": origin},
                ) as client:
                    session = await client.post("/api/v1/local/session")
                    auth = {"X-ICT-Local-Token": session.json()["token"]}
                    task_response = await client.get(
                        f"/api/v1/local/reproductions/{task_id}",
                        headers=auth,
                    )
                    self.assertEqual(task_response.status_code, 200, task_response.text)
                    self.assertEqual(task_response.json()["status"], "awaiting_review")
                    self.assertEqual(task_response.json()["assessment_state"], "not_assessed")

                    workflow_response = await client.get(
                        f"/api/v1/local/workflows/{workflow_id}",
                        headers=auth,
                    )
                    self.assertEqual(workflow_response.status_code, 200, workflow_response.text)
                    self.assertEqual(workflow_response.json()["owner_type"], "reproduction")
                    self.assertEqual(workflow_response.json()["revision"], 2)

                    run_response = await client.get(f"/api/v1/local/runs/{run_id}", headers=auth)
                    self.assertEqual(run_response.status_code, 200, run_response.text)
                    self.assertEqual(run_response.json()["status"], "succeeded")
                    self.assertEqual(run_response.json()["events"][-1]["status"], "SUCCEEDED")

                    report_response = await client.get(
                        f"/api/v1/local/artifacts/{report_id}/csv-preflight-report",
                        headers=auth,
                    )
                    self.assertEqual(report_response.status_code, 200, report_response.text)
                    self.assertEqual(report_response.json()["label"], "结构预检，非科研结果")

            asyncio.run(reopen_and_read())

    def test_local_reproduction_routes_require_local_session_and_reject_unknown_task(self) -> None:
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
                    unauthenticated = await client.get("/api/v1/local/reproductions")
                    self.assertEqual(unauthenticated.status_code, 401)
                    session = await client.post("/api/v1/local/session")
                    auth = {"X-ICT-Local-Token": session.json()["token"]}
                    invalid = await client.post(
                        "/api/v1/local/reproductions",
                        json={"title": "   ", "kind": "unknown"},
                        headers=auth,
                    )
                    self.assertEqual(invalid.status_code, 422)
                    oversized_baseline = await client.post(
                        "/api/v1/local/reproductions",
                        json={
                            "title": "超出限制的本机任务",
                            "kind": "paper",
                            "baseline": {"note": "x" * (64 * 1024)},
                        },
                        headers=auth,
                    )
                    self.assertEqual(oversized_baseline.status_code, 422)
                    missing = await client.get("/api/v1/local/reproductions/missing-task", headers=auth)
                    self.assertEqual(missing.status_code, 404)

            asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
