"""The local CSV node creates an aggregate, explicitly non-research artifact."""

import asyncio
import json
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class LocalCsvPreflightTests(unittest.TestCase):
    def test_preflight_persists_safe_aggregate_report_and_input_lineage(self) -> None:
        from app.services.local_artifacts import LocalArtifactStore
        from app.services.local_csv_executor import run_local_csv_preflight

        content = (
            b"record_id,group_id,split,label\n"
            b"sensitive-row-001,group-1,train,case-a\n"
            b"sensitive-row-002,group-2,test,case-b\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            store = LocalArtifactStore(Path(directory))
            source = store.import_csv(
                BytesIO(content),
                file_name="authorized.csv",
                authorization_confirmed=True,
            )
            node = {
                "id": "csv-check",
                "component_id": "ict.data.csv_manifest_preflight",
                "parameters": {"artifact_id": source.artifact_id},
            }

            result = asyncio.run(run_local_csv_preflight(node, {}, store))

            self.assertEqual(set(result), {"quality_report"})
            report_handle = result["quality_report"]
            resolved = store.resolve(report_handle["artifact_id"])
            report_bytes = resolved.path.read_bytes()
            report = json.loads(report_bytes)
            self.assertEqual(report["input"]["sha256"], source.sha256)
            self.assertEqual(report["row_count"], 2)
            self.assertFalse(report["research_result"])
            self.assertEqual(report["label"], "结构预检，非科研结果")
            self.assertNotIn(b"sensitive-row", report_bytes)

    def test_unavailable_local_artifact_fails_with_stable_node_error(self) -> None:
        from app.services.local_artifacts import LocalArtifactStore
        from app.services.local_csv_executor import run_local_csv_preflight
        from app.services.workflow_scheduler import WorkflowNodeFailure

        with tempfile.TemporaryDirectory() as directory:
            store = LocalArtifactStore(Path(directory))
            node = {
                "id": "csv-check",
                "component_id": "ict.data.csv_manifest_preflight",
                "parameters": {"artifact_id": "missing-artifact"},
            }

            with self.assertRaises(WorkflowNodeFailure) as raised:
                asyncio.run(run_local_csv_preflight(node, {}, store))

            self.assertEqual(raised.exception.code, "ARTIFACT_NOT_FOUND")

    def test_compiled_csv_node_runs_through_the_static_ready_queue(self) -> None:
        from app.services.local_artifacts import LocalArtifactStore
        from app.services.local_csv_executor import build_local_executor_registry
        from app.services.workflow_execution import compile_execution_plan
        from app.services.workflow_scheduler import execute_execution_plan

        content = b"record_id,group_id,split,label\nr1,g1,train,a\n"
        with tempfile.TemporaryDirectory() as directory:
            store = LocalArtifactStore(Path(directory))
            source = store.import_csv(
                BytesIO(content),
                file_name="manifest.csv",
                authorization_confirmed=True,
            )
            graph = {
                "schema_version": "ict.workflow.v1",
                "nodes": [
                    {
                        "id": "csv-check",
                        "type": "research",
                        "position": {"x": 25, "y": 30},
                        "data": {
                            "component_id": "ict.data.csv_manifest_preflight",
                            "component_version": "1.0.0",
                            "parameters": {"artifact_id": source.artifact_id},
                        },
                    }
                ],
                "edges": [],
            }
            plan = compile_execution_plan(graph, target_node_ids=["csv-check"])
            result = asyncio.run(
                execute_execution_plan(
                    plan,
                    executors=build_local_executor_registry(store),
                )
            )

            self.assertEqual(result["status"], "SUCCEEDED")
            self.assertEqual(result["node_runs"][0]["status"], "SUCCEEDED")
            report_handle = result["node_runs"][0]["output"]["quality_report"]
            report_path = store.resolve(report_handle["artifact_id"]).path
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertFalse(report["research_result"])
            self.assertEqual(report["input"]["sha256"], source.sha256)


    def test_connected_csv_source_flows_through_typed_preflight_dag(self) -> None:
        from app.services.local_artifacts import LocalArtifactStore
        from app.services.local_csv_executor import build_local_executor_registry
        from app.services.workflow_execution import compile_execution_plan
        from app.services.workflow_scheduler import execute_execution_plan

        content = b"record_id,group_id,split,label\nr1,g1,train,a\nr2,g2,test,b\n"
        with tempfile.TemporaryDirectory() as directory:
            store = LocalArtifactStore(Path(directory))
            source_artifact = store.import_csv(
                BytesIO(content),
                file_name="manifest.csv",
                authorization_confirmed=True,
            )
            graph = {
                "schema_version": "ict.workflow.v1",
                "nodes": [
                    {
                        "id": "source",
                        "type": "research",
                        "position": {"x": 20, "y": 40},
                        "data": {
                            "component_id": "ict.data.csv_artifact_source",
                            "component_version": "1.0.0",
                            "parameters": {"artifact_id": source_artifact.artifact_id},
                        },
                    },
                    {
                        "id": "preflight",
                        "type": "research",
                        "position": {"x": 320, "y": 40},
                        "data": {
                            "component_id": "ict.data.csv_manifest_preflight_input",
                            "component_version": "1.0.0",
                            "parameters": {},
                        },
                    },
                ],
                "edges": [
                    {
                        "id": "csv-to-preflight",
                        "source": "source",
                        "sourceHandle": "out:csv",
                        "target": "preflight",
                        "targetHandle": "in:csv",
                    }
                ],
            }
            plan = compile_execution_plan(graph, target_node_ids=["preflight"])
            result = asyncio.run(
                execute_execution_plan(
                    plan,
                    executors=build_local_executor_registry(store),
                )
            )

            self.assertEqual(plan["node_order"], ["source", "preflight"])
            self.assertEqual(result["status"], "SUCCEEDED")
            source_run, preflight_run = result["node_runs"]
            self.assertEqual(source_run["status"], "SUCCEEDED")
            self.assertEqual(
                source_run["output"]["csv"]["artifact_id"], source_artifact.artifact_id
            )
            self.assertEqual(preflight_run["status"], "SUCCEEDED")
            report_handle = preflight_run["output"]["quality_report"]
            report = store.read_csv_preflight_report(report_handle["artifact_id"])
            self.assertEqual(report["row_count"], 2)
            self.assertFalse(report["research_result"])


if __name__ == "__main__":
    unittest.main()
