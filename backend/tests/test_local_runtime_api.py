"""The local runtime imports data and runs a CSV workflow without platform services."""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

import httpx


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class LocalRuntimeApiTests(unittest.TestCase):
    def test_local_csv_run_is_persisted_and_available_without_platform_database(self) -> None:
        from app.local_runtime import create_local_runtime_app

        with tempfile.TemporaryDirectory() as directory:
            app = create_local_runtime_app(root=Path(directory))

            async def run_flow():
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://127.0.0.1:8766",
                    headers={"Origin": "http://127.0.0.1:5173"},
                ) as client:
                    session = await client.post("/api/v1/local/session")
                    self.assertEqual(session.status_code, 200)
                    auth = {"X-ICT-Local-Token": session.json()["token"]}
                    uploaded = await client.post(
                        "/api/v1/local/artifacts",
                        content=b"record_id,group_id,split,label\nr1,g1,train,a\n",
                        headers={
                            **auth,
                            "Content-Type": "application/octet-stream",
                            "X-Artifact-File-Name": "manifest.csv",
                            "X-ICT-Local-Consent": "confirmed",
                        },
                    )
                    self.assertEqual(uploaded.status_code, 201)
                    artifact_id = uploaded.json()["artifact_id"]
                    graph = {
                        "schema_version": "ict.workflow.v1",
                        "nodes": [
                            {
                                "id": "csv-check",
                                "type": "research",
                                "position": {"x": 10, "y": 20},
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
                        "/api/v1/local/workflows/local-workflow/draft",
                        json={"revision": 1, "graph": graph},
                        headers=auth,
                    )
                    self.assertEqual(saved.status_code, 200)
                    submitted = await client.post(
                        "/api/v1/local/workflows/local-workflow/runs",
                        json={"target_node_ids": ["csv-check"]},
                        headers=auth,
                    )
                    self.assertEqual(submitted.status_code, 202)
                    run_id = submitted.json()["run_id"]
                    for _ in range(100):
                        status = await client.get(f"/api/v1/local/runs/{run_id}", headers=auth)
                        self.assertEqual(status.status_code, 200)
                        if status.json()["status"] in {"succeeded", "partially_succeeded", "failed"}:
                            return status.json()
                        await asyncio.sleep(0.01)
                    self.fail("local workflow run did not reach a terminal state")

            detail = asyncio.run(run_flow())

            self.assertEqual(detail["status"], "succeeded")
            self.assertEqual(detail["node_runs"][0]["status"], "SUCCEEDED")
            self.assertEqual(detail["events"][0]["status"], "QUEUED")
            self.assertTrue((Path(directory) / "runtime.sqlite3").is_file())

    def test_offline_platform_node_is_blocked_while_independent_local_csv_branch_runs(self) -> None:
        from app.local_runtime import create_local_runtime_app

        with tempfile.TemporaryDirectory() as directory:
            app = create_local_runtime_app(root=Path(directory))

            async def run_flow():
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://127.0.0.1:8766",
                    headers={"Origin": "http://127.0.0.1:5173"},
                ) as client:
                    session = await client.post("/api/v1/local/session")
                    auth = {"X-ICT-Local-Token": session.json()["token"]}
                    upload = await client.post(
                        "/api/v1/local/artifacts",
                        content=b"record_id,group_id,split,label\nr1,g1,train,a\n",
                        headers={
                            **auth,
                            "Content-Type": "application/octet-stream",
                            "X-Artifact-File-Name": "manifest.csv",
                            "X-ICT-Local-Consent": "confirmed",
                        },
                    )
                    self.assertEqual(upload.status_code, 201)
                    artifact_id = upload.json()["artifact_id"]
                    graph = {
                        "schema_version": "ict.workflow.v1",
                        "nodes": [
                            {
                                "id": "csv-check",
                                "type": "research",
                                "position": {"x": 10, "y": 20},
                                "data": {
                                    "component_id": "ict.data.csv_manifest_preflight",
                                    "component_version": "1.0.0",
                                    "parameters": {"artifact_id": artifact_id},
                                },
                            },
                            {
                                "id": "platform-dataset",
                                "type": "research",
                                "position": {"x": 10, "y": 100},
                                "data": {
                                    "component_id": "ict.data.dataset_reference",
                                    "component_version": "1.0.0",
                                    "parameters": {"dataset_id": "dataset-x", "dataset_version": "v1"},
                                },
                            },
                        ],
                        "edges": [],
                    }
                    await client.put(
                        "/api/v1/local/workflows/hybrid-workflow/draft",
                        json={"revision": 1, "graph": graph},
                        headers=auth,
                    )
                    submitted = await client.post(
                        "/api/v1/local/workflows/hybrid-workflow/runs",
                        json={"target_node_ids": ["csv-check", "platform-dataset"]},
                        headers=auth,
                    )
                    self.assertEqual(submitted.status_code, 202)
                    run_id = submitted.json()["run_id"]
                    for _ in range(100):
                        response = await client.get(f"/api/v1/local/runs/{run_id}", headers=auth)
                        if response.json()["status"] in {"succeeded", "partially_succeeded", "failed"}:
                            return response.json()
                        await asyncio.sleep(0.01)
                    self.fail("hybrid local run did not reach a terminal state")

            result = asyncio.run(run_flow())
            node_states = {item["node_id"]: item["status"] for item in result["node_runs"]}

            self.assertEqual(result["status"], "partially_succeeded")
            self.assertEqual(node_states["csv-check"], "SUCCEEDED")
            self.assertEqual(node_states["platform-dataset"], "BLOCKED")

    def test_local_upload_requires_token_and_explicit_authorization(self) -> None:
        from app.local_runtime import create_local_runtime_app

        with tempfile.TemporaryDirectory() as directory:
            app = create_local_runtime_app(root=Path(directory))

            async def requests():
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://127.0.0.1:8766",
                    headers={"Origin": "http://127.0.0.1:5173"},
                ) as client:
                    missing_token = await client.post("/api/v1/local/artifacts", content=b"x")
                    session = await client.post("/api/v1/local/session")
                    missing_consent = await client.post(
                        "/api/v1/local/artifacts",
                        content=b"x",
                        headers={
                            "X-ICT-Local-Token": session.json()["token"],
                            "X-Artifact-File-Name": "manifest.csv",
                        },
                    )
                    wrong_origin = await client.get(
                        "/api/v1/local/workflow-components",
                        headers={"Origin": "http://evil.example", "X-ICT-Local-Token": session.json()["token"]},
                    )
                    return missing_token, missing_consent, wrong_origin

            missing_token, missing_consent, wrong_origin = asyncio.run(requests())

            self.assertEqual(missing_token.status_code, 401)
            self.assertNotIn("X-ICT-Local-Token", missing_token.text)
            self.assertEqual(missing_consent.status_code, 400)
            self.assertEqual(missing_consent.json()["error"]["code"], "ARTIFACT_AUTHORIZATION_REQUIRED")
            self.assertEqual(wrong_origin.status_code, 403)

    def test_same_origin_browser_get_without_origin_header_is_authorized(self) -> None:
        from app.local_runtime import create_local_runtime_app

        with tempfile.TemporaryDirectory() as directory:
            origin = "http://127.0.0.1:8766"
            app = create_local_runtime_app(
                root=Path(directory),
                allowed_origins={origin},
            )

            async def requests():
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url=origin,
                    headers={"Origin": origin},
                ) as session_client:
                    session = await session_client.post("/api/v1/local/session")
                    self.assertEqual(session.status_code, 200)

                auth = {"X-ICT-Local-Token": session.json()["token"]}
                async with httpx.AsyncClient(transport=transport, base_url=origin) as same_origin_client:
                    same_origin = await same_origin_client.get(
                        "/api/v1/local/workflow-components",
                        headers={**auth, "Sec-Fetch-Site": "same-origin"},
                    )
                    missing_fetch_metadata = await same_origin_client.get(
                        "/api/v1/local/workflow-components",
                        headers=auth,
                    )
                    different_loopback_origin = await same_origin_client.get(
                        "/api/v1/local/workflow-components",
                        headers={
                            **auth,
                            "Origin": "http://127.0.0.1:8767",
                            "Sec-Fetch-Site": "same-site",
                        },
                    )
                    return same_origin, missing_fetch_metadata, different_loopback_origin

            same_origin, missing_fetch_metadata, different_loopback_origin = asyncio.run(requests())

            self.assertEqual(same_origin.status_code, 200)
            self.assertIsInstance(same_origin.json(), list)
            self.assertEqual(missing_fetch_metadata.status_code, 401)
            self.assertEqual(different_loopback_origin.status_code, 401)


if __name__ == "__main__":
    unittest.main()
