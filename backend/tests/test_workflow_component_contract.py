"""Versioned execution contract fields required by the workflow compiler."""

import sys
import unittest
import asyncio
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class WorkflowComponentContractTests(unittest.TestCase):
    def test_components_declare_execution_target_dependencies_and_resource_limits(self) -> None:
        from app.services.workflow_components import list_workflow_components

        allowed_targets = {"local", "network", "platform"}
        required_resource_fields = {
            "cpu_millicores",
            "memory_mb",
            "gpu_count",
            "gpu_memory_mb",
            "timeout_seconds",
            "max_input_bytes",
        }

        for component in list_workflow_components():
            with self.subTest(component=component["component_id"]):
                self.assertEqual(component["schema_version"], "ict.component.v1")
                self.assertIn(component["execution_target"], allowed_targets)
                self.assertIsInstance(component["dependencies"], list)
                self.assertTrue(component["implementation_digest"] is None or len(component["implementation_digest"]) == 64)
                self.assertTrue(required_resource_fields.issubset(component["resource_limits"]))
                self.assertTrue(component["permissions"])
                self.assertTrue(all(isinstance(item, str) and item for item in component["permissions"]))

    def test_local_runtime_resolves_only_installed_local_executors_as_available(self) -> None:
        from app.services.workflow_components import list_workflow_components

        local_components = list_workflow_components(available_execution_targets={"local"})
        csv_component = next(
            item for item in local_components
            if item["component_id"] == "ict.data.csv_manifest_preflight"
        )
        platform_components = list_workflow_components(available_execution_targets={"platform"})
        platform_csv = next(
            item for item in platform_components
            if item["component_id"] == "ict.data.csv_manifest_preflight"
        )

        self.assertTrue(csv_component["execution_available"])
        self.assertFalse(platform_csv["execution_available"])

    def test_execution_plan_carries_resolved_execution_contract(self) -> None:
        from app.services.workflow_execution import compile_execution_plan

        graph = {
            "schema_version": "ict.workflow.v1",
            "nodes": [
                {
                    "id": "dataset",
                    "type": "research",
                    "position": {"x": 0, "y": 0},
                    "data": {
                        "component_id": "ict.data.dataset_reference",
                        "component_version": "1.0.0",
                        "parameters": {"dataset_id": "ds", "dataset_version": "v1"},
                    },
                }
            ],
            "edges": [],
        }
        plan = compile_execution_plan(graph, target_node_ids=["dataset"])

        self.assertEqual(plan["nodes"][0]["component_schema_version"], "ict.component.v1")
        self.assertEqual(plan["nodes"][0]["execution_target"], "platform")
        self.assertEqual(len(plan["nodes"][0]["component_contract_hash"]), 64)

    def test_component_catalog_api_exposes_the_versioned_execution_contract(self) -> None:
        import httpx
        from app.main import create_app

        app = create_app(auth_tokens={"operator": "component-token", "viewer": "viewer-component-token"})

        async def request_catalog():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://ict.test",
            ) as client:
                return await client.get(
                    "/api/v1/workflow-components",
                    headers={"Authorization": "Bearer component-token"},
                )

        response = asyncio.run(request_catalog())

        self.assertEqual(response.status_code, 200)
        item = response.json()[0]
        self.assertEqual(item["schema_version"], "ict.component.v1")
        self.assertIn(item["execution_target"], {"local", "network", "platform"})
        self.assertIn("gpu_memory_mb", item["resource_limits"])


if __name__ == "__main__":
    unittest.main()
