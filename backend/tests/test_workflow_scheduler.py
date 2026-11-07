"""Ready queue, failure isolation, and external-wait behavior."""

import asyncio
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class WorkflowSchedulerTests(unittest.TestCase):
    def test_failed_branch_blocks_only_its_descendants_and_external_wait_is_visible(self) -> None:
        from app.services.workflow_scheduler import ExternalWait, execute_execution_plan

        plan = {
            "node_order": ["root", "bad", "blocked", "independent", "network"],
            "nodes": [
                {"id": node_id, "component_id": node_id, "parameters": {}}
                for node_id in ("root", "bad", "blocked", "independent", "network")
            ],
            "edges": [
                {"id": "root-bad", "source": "root", "target": "bad", "source_handle": "out:x", "target_handle": "in:x"},
                {"id": "bad-blocked", "source": "bad", "target": "blocked", "source_handle": "out:x", "target_handle": "in:x"},
            ],
        }
        external_completion = asyncio.Event()

        def fail(_node, _inputs):
            raise RuntimeError("controlled test failure")

        async def wait_for_external(_node, _inputs):
            return await external_completion.wait()

        events = []
        async def run():
            task = asyncio.create_task(
                execute_execution_plan(
                    plan,
                    executors={
                        "root": lambda _node, _inputs: {"root": True},
                        "bad": fail,
                        "independent": lambda _node, _inputs: {"independent": True},
                        "network": lambda _node, _inputs: ExternalWait(wait_for_external(None, None)),
                    },
                    on_event=events.append,
                    max_concurrency=3,
                )
            )
            for _ in range(20):
                await asyncio.sleep(0)
                if any(event["node_id"] == "network" and event["status"] == "WAITING_EXTERNAL" for event in events):
                    break
            external_completion.set()
            return await task

        result = asyncio.run(run())
        states = {item["node_id"]: item["status"] for item in result["node_runs"]}

        self.assertEqual(result["status"], "PARTIALLY_SUCCEEDED")
        self.assertEqual(states["bad"], "FAILED")
        self.assertEqual(states["blocked"], "BLOCKED")
        self.assertEqual(states["independent"], "SUCCEEDED")
        self.assertEqual(states["network"], "SUCCEEDED")
        self.assertTrue(any(event["status"] == "WAITING_EXTERNAL" for event in events))

    def test_cancelling_an_external_wait_marks_the_node_and_run_cancelled(self) -> None:
        from app.services.workflow_scheduler import ExternalWait, execute_execution_plan

        plan = {
            "node_order": ["network"],
            "nodes": [{"id": "network", "component_id": "network", "parameters": {}}],
            "edges": [],
        }
        events = []
        external_gate = asyncio.Event()

        async def wait_for_external(_node, _inputs):
            return await external_gate.wait()

        async def run_and_cancel():
            task = asyncio.create_task(
                execute_execution_plan(
                    plan,
                    executors={
                        "network": lambda _node, _inputs: ExternalWait(
                            wait_for_external(None, None), operation_code="NETWORK_REQUEST"
                        )
                    },
                    on_event=events.append,
                )
            )
            for _ in range(20):
                await asyncio.sleep(0)
                if any(event["status"] == "WAITING_EXTERNAL" for event in events):
                    break
            task.cancel()
            return await task

        result = asyncio.run(run_and_cancel())

        self.assertEqual(result["status"], "CANCELLED")
        self.assertEqual(result["node_runs"][0]["status"], "CANCELLED")

    def test_external_wait_timeout_blocks_only_dependents_and_cancels_awaitable(self) -> None:
        from app.services.workflow_scheduler import ExternalWait, execute_execution_plan

        plan = {
            "node_order": ["network", "blocked", "independent"],
            "nodes": [
                {
                    "id": "network",
                    "component_id": "network",
                    "parameters": {},
                    "resource_limits": {"timeout_seconds": 1},
                },
                {"id": "blocked", "component_id": "blocked", "parameters": {}},
                {"id": "independent", "component_id": "independent", "parameters": {}},
            ],
            "edges": [{"id": "network-blocked", "source": "network", "target": "blocked"}],
        }
        external_gate = asyncio.Event()
        cancellation_observed = asyncio.Event()
        events = []

        async def wait_for_external(_node, _inputs):
            try:
                await external_gate.wait()
                return {"out:value": "late"}
            except asyncio.CancelledError:
                cancellation_observed.set()
                raise

        async def release_external_gate_late():
            await asyncio.sleep(1.1)
            external_gate.set()

        async def run():
            release_task = asyncio.create_task(release_external_gate_late())
            result = await execute_execution_plan(
                plan,
                executors={
                    "network": lambda _node, _inputs: ExternalWait(
                        wait_for_external(None, None), operation_code="NETWORK_REQUEST"
                    ),
                    "blocked": lambda _node, _inputs: {"unexpected": True},
                    "independent": lambda _node, _inputs: {"independent": True},
                },
                on_event=events.append,
                max_concurrency=2,
            )
            await release_task
            return result

        result = asyncio.run(run())
        states = {item["node_id"]: item["status"] for item in result["node_runs"]}
        error_codes = {item["node_id"]: item["error_code"] for item in result["node_runs"]}

        self.assertEqual(result["status"], "PARTIALLY_SUCCEEDED")
        self.assertEqual(states["network"], "FAILED")
        self.assertEqual(error_codes["network"], "EXTERNAL_WAIT_TIMEOUT")
        self.assertEqual(states["blocked"], "BLOCKED")
        self.assertEqual(states["independent"], "SUCCEEDED")
        self.assertTrue(cancellation_observed.is_set())
        self.assertTrue(any(event["status"] == "WAITING_EXTERNAL" for event in events))

    def test_executor_timeout_error_is_not_reported_as_external_wait_timeout(self) -> None:
        from app.services.workflow_scheduler import execute_execution_plan

        plan = {
            "node_order": ["local"],
            "nodes": [{"id": "local", "component_id": "local", "parameters": {}}],
            "edges": [],
        }

        def timeout(_node, _inputs):
            raise TimeoutError("component-defined timeout")

        result = asyncio.run(execute_execution_plan(plan, executors={"local": timeout}))

        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["node_runs"][0]["error_code"], "NODE_EXECUTION_TIMEOUT")


    def test_join_waits_for_all_distinct_parents_before_running(self) -> None:
        from app.services.workflow_scheduler import execute_execution_plan

        plan = {
            "node_order": ["source", "delayed", "join", "independent"],
            "nodes": [
                {"id": node_id, "component_id": node_id, "parameters": {}}
                for node_id in ("source", "delayed", "join", "independent")
            ],
            "edges": [
                {"id": "source-x", "source": "source", "target": "join", "target_handle": "in:x"},
                {"id": "source-y", "source": "source", "target": "join", "target_handle": "in:y"},
                {"id": "delayed-join", "source": "delayed", "target": "join", "target_handle": "in:z"},
            ],
        }
        delayed_started = asyncio.Event()
        release_delayed = asyncio.Event()
        join_started = asyncio.Event()

        async def delayed_executor(_node, _inputs):
            delayed_started.set()
            await release_delayed.wait()
            return {"out:value": "delayed"}

        def join_executor(_node, _inputs):
            join_started.set()
            return {"joined": True}

        async def run():
            task = asyncio.create_task(
                execute_execution_plan(
                    plan,
                    executors={
                        "source": lambda _node, _inputs: {"out:value": "source"},
                        "delayed": delayed_executor,
                        "join": join_executor,
                        "independent": lambda _node, _inputs: {"independent": True},
                    },
                    max_concurrency=4,
                )
            )
            await asyncio.wait_for(delayed_started.wait(), timeout=1)
            await asyncio.sleep(0.02)
            self.assertFalse(join_started.is_set())
            release_delayed.set()
            return await task

        result = asyncio.run(run())
        states = {item["node_id"]: item["status"] for item in result["node_runs"]}
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(states["join"], "SUCCEEDED")
        self.assertTrue(join_started.is_set())

    def test_dependency_index_deduplicates_multi_port_parent_and_orders_children(self) -> None:
        from app.services.workflow_scheduler import _build_dependency_index

        node_order = ["source", "second", "join", "tail"]
        edges = [
            {"source": "source", "target": "join"},
            {"source": "source", "target": "join"},
            {"source": "second", "target": "join"},
            {"source": "join", "target": "tail"},
        ]

        parents, children = _build_dependency_index(node_order, edges)

        self.assertEqual(parents["join"], {"source", "second"})
        self.assertEqual(children["source"], ["join"])
        self.assertEqual(children["join"], ["tail"])


if __name__ == "__main__":
    unittest.main()
