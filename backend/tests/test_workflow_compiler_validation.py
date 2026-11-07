"""Compiler validation and target-selection regressions."""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class WorkflowCompilerValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        from app.services.workflow_execution import compile_execution_plan

        self.compile = compile_execution_plan
        self.graph = {
            "schema_version": "ict.workflow.v1",
            "nodes": [
                {
                    "id": "source",
                    "type": "research",
                    "position": {"x": 0, "y": 0},
                    "data": {
                        "component_id": "ict.data.dataset_reference",
                        "component_version": "1.0.0",
                        "parameters": {"dataset_id": "dataset-a", "dataset_version": "v1"},
                    },
                },
                {
                    "id": "output",
                    "type": "research",
                    "position": {"x": 100, "y": 0},
                    "data": {
                        "component_id": "ict.data.quality_check",
                        "component_version": "1.0.0",
                        "parameters": {"rule_set_id": "generic-manifest-v1"},
                    },
                },
                {
                    "id": "unused",
                    "type": "research",
                    "position": {"x": 100, "y": 100},
                    "data": {"component_id": "not.registered", "parameters": {}},
                },
            ],
            "edges": [
                {
                    "id": "source-output",
                    "source": "source",
                    "target": "output",
                    "sourceHandle": "out:dataset",
                    "targetHandle": "in:dataset",
                }
            ],
        }

    def test_unknown_target_is_rejected_with_stable_code(self) -> None:
        from app.services.workflow_execution import WorkflowCompilationError

        with self.assertRaises(WorkflowCompilationError) as raised:
            self.compile(self.graph, target_node_ids=["missing"])

        self.assertEqual(raised.exception.code, "TARGET_NODE_NOT_FOUND")

    def test_invalid_unused_component_does_not_block_selected_output(self) -> None:
        plan = self.compile(self.graph, target_node_ids=["output"])

        self.assertEqual(plan["node_order"], ["source", "output"])
        self.assertNotIn("unused", {node["id"] for node in plan["nodes"]})

    def test_cycle_in_selected_ancestors_is_rejected(self) -> None:
        from app.services.workflow_execution import WorkflowCompilationError

        cyclic_graph = {
            **self.graph,
            "edges": [
                *self.graph["edges"],
                {
                    "id": "output-source",
                    "source": "output",
                    "target": "source",
                    "sourceHandle": "out:validated_dataset",
                    "targetHandle": "in:dataset",
                },
            ],
        }

        with self.assertRaises(WorkflowCompilationError) as raised:
            self.compile(cyclic_graph, target_node_ids=["output"])

        self.assertEqual(raised.exception.code, "CYCLE_UNSUPPORTED")

    def test_component_string_max_length_is_enforced_during_compilation(self) -> None:
        from app.services.workflow_execution import WorkflowCompilationError

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
                        "parameters": {"doi": "x" * 300},
                    },
                }
            ],
            "edges": [],
        }
        # The exact schema boundary remains valid.
        self.compile(graph, target_node_ids=["doi"])

        graph["nodes"][0]["data"]["parameters"]["doi"] += "x"
        with self.assertRaises(WorkflowCompilationError) as raised:
            self.compile(graph, target_node_ids=["doi"])

        self.assertEqual(raised.exception.code, "PARAMETER_MAX_LENGTH_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
