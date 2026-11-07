"""Workflow compiler tests use only the registered versioned component contracts."""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class WorkflowExecutionPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        from app.services.workflow_execution import compile_execution_plan

        self.compile = compile_execution_plan
        self.graph = {
            "schema_version": "ict.workflow.v1",
            "nodes": [
                {
                    "id": "dataset",
                    "type": "research",
                    "position": {"x": 10, "y": 20},
                    "data": {
                        "component_id": "ict.data.dataset_reference",
                        "component_version": "1.0.0",
                        "parameters": {"dataset_id": "dataset-a", "dataset_version": "v1"},
                    },
                },
                {
                    "id": "quality",
                    "type": "research",
                    "position": {"x": 220, "y": 20},
                    "data": {
                        "component_id": "ict.data.quality_check",
                        "component_version": "1.0.0",
                        "parameters": {"rule_set_id": "generic-manifest-v1"},
                    },
                },
                {
                    "id": "unused",
                    "type": "research",
                    "position": {"x": 220, "y": 180},
                    "data": {
                        "component_id": "ict.data.dataset_reference",
                        "component_version": "1.0.0",
                        "parameters": {"dataset_id": "dataset-b", "dataset_version": "v2"},
                    },
                },
            ],
            "edges": [
                {
                    "id": "dataset-to-quality",
                    "source": "dataset",
                    "target": "quality",
                    "sourceHandle": "out:dataset",
                    "targetHandle": "in:dataset",
                },
            ],
        }

    def test_compiler_keeps_only_requested_ancestors_and_hash_ignores_layout(self) -> None:
        plan = self.compile(self.graph, target_node_ids=["quality"])

        self.assertEqual(plan["target_node_ids"], ["quality"])
        self.assertEqual(plan["node_order"], ["dataset", "quality"])
        self.assertEqual({node["id"] for node in plan["nodes"]}, {"dataset", "quality"})
        self.assertEqual(len(plan["plan_hash"]), 64)

        moved_graph = {
            **self.graph,
            "nodes": [
                {**node, "position": {"x": 900, "y": -40}}
                for node in self.graph["nodes"]
            ],
        }
        moved_plan = self.compile(moved_graph, target_node_ids=["quality"])

        self.assertEqual(moved_plan["plan_hash"], plan["plan_hash"])


if __name__ == "__main__":
    unittest.main()
