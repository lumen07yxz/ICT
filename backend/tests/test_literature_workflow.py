"""Exercise literature queries through the persisted local workflow API."""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.local_runtime import create_local_runtime_app
from app.services.workflow_execution import WorkflowCompilationError, compile_execution_plan


def literature_graph(parameters=None, *, connected=True):
    return {
        "schema_version": "ict.workflow.v1",
        "nodes": [
            {"id": "output", "position": {"x": 390, "y": 40}, "data": {
                "component_id": "ict.paper.result_output", "component_version": "1.0.0", "parameters": {},
            }},
            {"id": "search", "position": {"x": 20, "y": 40}, "data": {
                "component_id": "ict.paper.literature_search", "component_version": "1.0.0",
                "parameters": parameters if parameters is not None else {"query": "医学影像"},
            }},
        ],
        "edges": [{"id": "flow", "source": "search", "sourceHandle": "out:papers",
                   "target": "output", "targetHandle": "in:items"}] if connected else [],
    }


class LiteratureWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def test_compile_rejects_missing_query_connection_and_invalid_options(self):
        cases = [
            (literature_graph({"query": "  "}), "PARAMETER_REQUIRED"),
            (literature_graph(connected=False), "REQUIRED_INPUT_UNCONNECTED"),
            (literature_graph({"query": "AI", "start_year": "2025", "end_year": "2020"}), "LITERATURE_YEAR_RANGE_INVALID"),
            (literature_graph({"query": "AI", "limit": "101"}), "LITERATURE_LIMIT_INVALID"),
            (literature_graph({"query": "AI", "source": "other"}), "LITERATURE_SOURCE_INVALID"),
        ]
        for graph, code in cases:
            with self.subTest(code=code), self.assertRaises(WorkflowCompilationError) as context:
                compile_execution_plan(graph, target_node_ids=["output"])
            self.assertEqual(context.exception.code, code)
        with self.assertRaises(WorkflowCompilationError) as context:
            compile_execution_plan(literature_graph(), target_node_ids=["search"])
        self.assertEqual(context.exception.code, "LITERATURE_OUTPUT_UNCONNECTED")

    async def test_search_dispatch_output_and_restart(self):
        requests = []

        async def crossref(request):
            requests.append(request.url)
            query = request.url.params["query.bibliographic"]
            if query == "unavailable":
                return httpx.Response(503)
            if query == "cancel":
                await asyncio.sleep(10)
            items = [] if query == "empty" else [{
                "title": [query], "DOI": "10.1234/paper", "URL": "https://doi.org/10.1234/paper",
                "author": [{"given": "Ada", "family": "Lovelace"}], "container-title": ["Journal"],
                "published": {"date-parts": [[2021, 2]]}, "abstract": "<jats:p>A &amp; B</jats:p>",
            }]
            return httpx.Response(200, json={"message": {"items": items}})

        base_url = "http://127.0.0.1:8767"
        origin = {"Origin": "http://127.0.0.1:5173"}
        run_ids = []
        real_client = httpx.AsyncClient
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_local_runtime_app(root=root)
            async with real_client(transport=httpx.ASGITransport(app=app), base_url=base_url, headers=origin) as client:
                session = await client.post("/api/v1/local/session")
                client.headers["X-ICT-Local-Token"] = session.json()["token"]

                async def submit(query, revision):
                    graph = literature_graph({"query": query, "start_year": "2020", "end_year": "2024", "limit": "3", "sort": "published"})
                    saved = await client.put("/api/v1/local/workflows/lit/draft", json={"revision": revision, "graph": graph})
                    self.assertEqual(saved.status_code, 200, saved.text)
                    if revision == 1:
                        stale = await client.post("/api/v1/local/workflows/lit/runs", json={
                            "target_node_ids": ["output"], "expected_revision": revision + 1,
                        })
                        self.assertEqual(stale.status_code, 409)
                        self.assertEqual(stale.json()["error"]["code"], "LOCAL_WORKFLOW_REVISION_CONFLICT")
                    submitted = await client.post("/api/v1/local/workflows/lit/runs", json={
                        "target_node_ids": ["output"], "expected_revision": revision,
                    })
                    self.assertEqual(submitted.status_code, 202, submitted.text)
                    self.assertEqual(submitted.json()["status"], "queued")
                    run_ids.append(submitted.json()["run_id"])
                    return f"/api/v1/local/runs/{run_ids[-1]}"

                async def wait_for(path, states):
                    for _ in range(150):
                        detail = (await client.get(path)).json()
                        if detail["status"] in states:
                            return detail
                        await asyncio.sleep(0.02)
                    self.fail(f"Expected {states}, got {detail['status']}")

                with patch("httpx.AsyncClient", side_effect=lambda **kw: real_client(transport=httpx.MockTransport(crossref), **kw)):
                    for revision, query in enumerate(("医学影像", "protein folding", "empty", "unavailable", "cancel"), 1):
                        path = await submit(query, revision)
                        if query == "cancel":
                            await wait_for(path, {"waiting_external"})
                            self.assertLess((await client.post(f"{path}/cancel")).status_code, 300)
                        run = await wait_for(path, {"succeeded", "failed", "cancelled", "partially_succeeded"})
                        self.assertEqual(run["execution_plan"]["node_order"], ["search", "output"])
                        nodes = {node["node_id"]: node for node in run["node_runs"]}
                        if query == "unavailable":
                            self.assertEqual(run["status"], "failed")
                            self.assertEqual(nodes["search"]["error_code"], "NETWORK_UPSTREAM_ERROR")
                            self.assertEqual(nodes["output"]["status"], "BLOCKED")
                        elif query == "cancel":
                            self.assertEqual(run["status"], "cancelled")
                        else:
                            self.assertEqual(run["status"], "succeeded")
                            expected = [] if query == "empty" else [{
                                "title": query, "authors": ["Ada Lovelace"], "publication_year": 2021,
                                "journal_or_venue": "Journal", "abstract": "A & B", "doi": "10.1234/paper",
                                "url": "https://doi.org/10.1234/paper", "source": "Crossref",
                            }]
                            self.assertEqual(nodes["output"]["output"], {"papers": expected})
                            self.assertEqual(nodes["search"]["output"], nodes["output"]["output"])
            self.assertEqual(len(requests), 5)
            self.assertEqual(requests[0].host, "api.crossref.org")
            self.assertEqual(requests[0].params["rows"], "3")
            self.assertEqual(requests[0].params["sort"], "published")
            self.assertIn("from-pub-date:2020-01-01", requests[0].params["filter"])
            self.assertIn("until-pub-date:2024-12-31", requests[0].params["filter"])

            restarted = create_local_runtime_app(root=root)
            async with real_client(transport=httpx.ASGITransport(app=restarted), base_url=base_url, headers=origin) as client:
                session = await client.post("/api/v1/local/session")
                client.headers["X-ICT-Local-Token"] = session.json()["token"]
                draft = (await client.get("/api/v1/local/workflows/lit/draft")).json()
                self.assertEqual(draft["revision"], 5)
                self.assertEqual(draft["graph"]["nodes"][0]["position"], {"x": 390, "y": 40})
                self.assertEqual(draft["graph"]["edges"][0]["targetHandle"], "in:items")
                persisted = (await client.get(f"/api/v1/local/runs/{run_ids[0]}")).json()
                output = next(node for node in persisted["node_runs"] if node["node_id"] == "output")
                self.assertEqual(output["output"]["papers"][0]["title"], "医学影像")
