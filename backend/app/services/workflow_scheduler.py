"""Bounded static-DAG scheduler with observable node and external-wait states."""

from __future__ import annotations

import asyncio
import heapq
import inspect
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Awaitable, Callable, Mapping


logger = logging.getLogger("ict.workflow.scheduler")
DEFAULT_EXTERNAL_WAIT_TIMEOUT_SECONDS = 600.0


class NodeRunStatus(StrEnum):
    WAITING = "WAITING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_EXTERNAL = "WAITING_EXTERNAL"
    SUCCEEDED = "SUCCEEDED"
    RESTORED = "RESTORED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CACHED = "CACHED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class WorkflowNodeFailure(RuntimeError):
    """Expected node failure with a stable code safe to persist and show in UI."""

    def __init__(self, code: str, message: str = "节点执行失败。"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ExternalWait:
    """Mark an executor awaitable as an external operation, such as a network call."""

    awaitable: Awaitable[Any]
    operation_code: str = "EXTERNAL_OPERATION"


@dataclass(frozen=True)
class CachedNodeOutput:
    """Return a previously persisted deterministic node output to the scheduler."""

    value: Any


Executor = Callable[[dict[str, Any], dict[str, Any]], Any | Awaitable[Any] | ExternalWait]
EventCallback = Callable[[dict[str, Any]], None]
NodeResultCallback = Callable[[dict[str, Any]], None]


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _port_id(handle: Any, prefix: str) -> str | None:
    if not isinstance(handle, str) or not handle.startswith(prefix):
        return None
    return handle[len(prefix) :]


def _build_dependency_index(
    node_order: list[str],
    edges: list[dict[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    """Index distinct parent nodes and stable child lists for incremental release."""
    parents: dict[str, set[str]] = {node_id: set() for node_id in node_order}
    child_sets: dict[str, set[str]] = {node_id: set() for node_id in node_order}
    order_index = {node_id: index for index, node_id in enumerate(node_order)}
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source not in parents or target not in parents:
            raise ValueError("execution plan edge endpoint is missing")
        parents[target].add(source)
        child_sets[source].add(target)
    children = {
        node_id: sorted(child_sets[node_id], key=order_index.__getitem__)
        for node_id in node_order
    }
    return parents, children


def _external_wait_timeout_seconds(node: dict[str, Any]) -> float:
    """Use the component's declared deadline, with a bounded fallback for generic executors."""
    limits = node.get("resource_limits")
    declared = limits.get("timeout_seconds") if isinstance(limits, dict) else None
    if isinstance(declared, (int, float)) and not isinstance(declared, bool) and declared >= 0:
        return float(declared)
    return DEFAULT_EXTERNAL_WAIT_TIMEOUT_SECONDS


async def execute_execution_plan(
    plan: dict[str, Any],
    *,
    executors: Mapping[str, Executor],
    max_concurrency: int = 4,
    on_event: EventCallback | None = None,
    restored_outputs: Mapping[str, Any] | None = None,
    on_node_result: NodeResultCallback | None = None,
) -> dict[str, Any]:
    """Run an immutable static DAG while isolating failures to dependent branches.

    Executors receive a resolved plan node and a map of upstream input-port IDs
    to output values. Production executors should pass ArtifactHandle references
    through this boundary instead of retaining large arrays or model objects.
    """
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be positive")

    nodes = plan.get("nodes")
    node_order = plan.get("node_order")
    edges = plan.get("edges")
    if not isinstance(nodes, list) or not isinstance(node_order, list) or not isinstance(edges, list):
        raise ValueError("execution plan is missing nodes, node_order, or edges")
    nodes_by_id = {node.get("id"): node for node in nodes if isinstance(node, dict)}
    if not nodes_by_id or len(nodes_by_id) != len(nodes) or set(node_order) != set(nodes_by_id):
        raise ValueError("execution plan node IDs are invalid")

    incoming_edges: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes_by_id}
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source not in nodes_by_id or target not in nodes_by_id:
            raise ValueError("execution plan edge endpoint is missing")
        incoming_edges[target].append(edge)
    parents, children = _build_dependency_index(node_order, edges)

    restored_outputs = dict(restored_outputs or {})
    if set(restored_outputs) - set(nodes_by_id):
        raise ValueError("restored output references a node outside the execution plan")

    states = {node_id: NodeRunStatus.WAITING for node_id in node_order}
    states.update({node_id: NodeRunStatus.RESTORED for node_id in restored_outputs})
    outputs: dict[str, Any] = dict(restored_outputs)
    errors: dict[str, str] = {}
    event_log: list[dict[str, Any]] = []
    event_sequence = 0

    def emit(
        node_id: str,
        status: NodeRunStatus,
        *,
        error_code: str | None = None,
        already_persisted: bool = False,
    ) -> None:
        nonlocal event_sequence
        event_sequence += 1
        event = {
            "sequence": event_sequence,
            "node_id": node_id,
            "status": status.value,
            "error_code": error_code,
            "occurred_at": _timestamp(),
        }
        event_log.append(event)
        if on_event is not None and not already_persisted:
            try:
                on_event(event)
            except Exception:
                # UI/event persistence failures must be logged without corrupting DAG state.
                logger.exception("workflow_event_callback_failed node_id=%s sequence=%s", node_id, event_sequence)

    def transition(
        node_id: str,
        status: NodeRunStatus,
        *,
        error_code: str | None = None,
        already_persisted: bool = False,
    ) -> None:
        states[node_id] = status
        if error_code is not None:
            errors[node_id] = error_code
        emit(node_id, status, error_code=error_code, already_persisted=already_persisted)

    def upstream_inputs(node_id: str) -> dict[str, Any]:
        input_values: dict[str, Any] = {}
        for edge in incoming_edges[node_id]:
            source_id = edge["source"]
            output_value = outputs[source_id]
            source_port = _port_id(edge.get("source_handle"), "out:")
            target_port = _port_id(edge.get("target_handle"), "in:")
            if isinstance(output_value, dict) and source_port in output_value:
                output_value = output_value[source_port]
            if target_port is None:
                continue
            if target_port in input_values:
                current = input_values[target_port]
                if not isinstance(current, list):
                    input_values[target_port] = [current]
                input_values[target_port].append(output_value)
            else:
                input_values[target_port] = output_value
        return input_values

    async def invoke(node_id: str) -> None:
        node = nodes_by_id[node_id]
        component_id = node.get("component_id")
        executor_binding = node.get("executor_binding")
        executor = executors.get(executor_binding) or executors.get(component_id)
        if executor is None:
            execution_target = node.get("execution_target")
            error_code = (
                "EXECUTION_TARGET_UNAVAILABLE"
                if execution_target in {"network", "platform"}
                else "EXECUTOR_UNAVAILABLE"
            )
            transition(node_id, NodeRunStatus.BLOCKED, error_code=error_code)
            logger.warning(
                "workflow_node_executor_unavailable node_id=%s component_id=%s executor_binding=%s execution_target=%s error_code=%s",
                node_id,
                component_id,
                executor_binding,
                execution_target,
                error_code,
            )
            return

        transition(node_id, NodeRunStatus.RUNNING)
        external_operation_code: str | None = None
        external_timeout_seconds: float | None = None
        try:
            value = executor(node, upstream_inputs(node_id))
            if isinstance(value, ExternalWait):
                external_operation_code = value.operation_code
                external_timeout_seconds = _external_wait_timeout_seconds(node)
                transition(node_id, NodeRunStatus.WAITING_EXTERNAL)
                # External operations must finish within the component's admitted time budget.
                value = await asyncio.wait_for(value.awaitable, timeout=external_timeout_seconds)
            elif inspect.isawaitable(value):
                value = await value
            result_status = NodeRunStatus.CACHED if isinstance(value, CachedNodeOutput) else NodeRunStatus.SUCCEEDED
            output = value.value if isinstance(value, CachedNodeOutput) else value
            if on_node_result is not None:
                try:
                    # Persist a completed output before allowing dependent nodes to run.
                    on_node_result(
                        {
                            "node_id": node_id,
                            "status": result_status.value,
                            "output": output,
                            "occurred_at": _timestamp(),
                        }
                    )
                except Exception:
                    logger.exception("workflow_node_result_persist_failed node_id=%s", node_id)
                    transition(node_id, NodeRunStatus.FAILED, error_code="NODE_RESULT_PERSISTENCE_FAILED")
                    return
            outputs[node_id] = output
            transition(node_id, result_status, already_persisted=on_node_result is not None)
        except asyncio.CancelledError:
            transition(node_id, NodeRunStatus.CANCELLED, error_code="RUN_CANCELLED")
            raise
        except WorkflowNodeFailure as error:
            logger.warning(
                "workflow_node_rejected node_id=%s component_id=%s error_code=%s",
                node_id,
                component_id,
                error.code,
            )
            transition(node_id, NodeRunStatus.FAILED, error_code=error.code)
        except TimeoutError:
            error_code = (
                "EXTERNAL_WAIT_TIMEOUT"
                if external_operation_code is not None
                else "NODE_EXECUTION_TIMEOUT"
            )
            logger.warning(
                "workflow_node_execution_timed_out node_id=%s component_id=%s operation_code=%s timeout_seconds=%s error_code=%s",
                node_id,
                component_id,
                external_operation_code,
                external_timeout_seconds,
                error_code,
            )
            transition(node_id, NodeRunStatus.FAILED, error_code=error_code)
        except Exception:
            logger.exception(
                "workflow_node_execution_failed node_id=%s component_id=%s",
                node_id,
                component_id,
            )
            transition(node_id, NodeRunStatus.FAILED, error_code="NODE_EXECUTION_FAILED")

    async def cancel_active(active: dict[asyncio.Task[None], str]) -> None:
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)

    active: dict[asyncio.Task[None], str] = {}
    ready: list[tuple[int, str]] = []
    order_index = {node_id: index for index, node_id in enumerate(node_order)}
    remaining_parent_count = {node_id: len(parent_ids) for node_id, parent_ids in parents.items()}

    # A restored node is already complete; remove its edge contribution before
    # scheduling so only unfinished parents remain as blockers.
    for node_id in restored_outputs:
        for child_id in children[node_id]:
            if states[child_id] == NodeRunStatus.WAITING:
                remaining_parent_count[child_id] -= 1

    def release_completed_node(completed_node_id: str) -> None:
        """Release only direct successors; propagate dependency blocks downstream."""
        completed: list[str] = [completed_node_id]
        while completed:
            parent_id = completed.pop()
            parent_status = states[parent_id]
            for child_id in children[parent_id]:
                if states[child_id] != NodeRunStatus.WAITING:
                    continue
                if parent_status in {
                    NodeRunStatus.FAILED,
                    NodeRunStatus.BLOCKED,
                    NodeRunStatus.CANCELLED,
                    NodeRunStatus.SKIPPED,
                }:
                    transition(child_id, NodeRunStatus.BLOCKED, error_code="DEPENDENCY_FAILED")
                    completed.append(child_id)
                    continue
                if parent_status not in {NodeRunStatus.SUCCEEDED, NodeRunStatus.CACHED, NodeRunStatus.RESTORED}:
                    continue
                remaining_parent_count[child_id] -= 1
                if remaining_parent_count[child_id] == 0:
                    transition(child_id, NodeRunStatus.READY)
                    heapq.heappush(ready, (order_index[child_id], child_id))

    try:
        for node_id in node_order:
            if states[node_id] == NodeRunStatus.WAITING and remaining_parent_count[node_id] == 0:
                transition(node_id, NodeRunStatus.READY)
                heapq.heappush(ready, (order_index[node_id], node_id))
        while ready or active:
            while ready and len(active) < max_concurrency:
                _index, node_id = heapq.heappop(ready)
                task = asyncio.create_task(invoke(node_id), name=f"workflow-node-{node_id}")
                active[task] = node_id
            if not active:
                break
            completed, _pending = await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
            for task in completed:
                node_id = active.pop(task)
                # invoke captures node exceptions; retrieve unexpected task errors for logging.
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
                except Exception:
                    logger.exception("workflow_scheduler_task_failed")
                    if states[node_id] in {NodeRunStatus.RUNNING, NodeRunStatus.WAITING_EXTERNAL}:
                        transition(node_id, NodeRunStatus.FAILED, error_code="SCHEDULER_TASK_FAILED")
                release_completed_node(node_id)
    except asyncio.CancelledError:
        await cancel_active(active)
        for node_id, status in list(states.items()):
            if status in {NodeRunStatus.WAITING, NodeRunStatus.READY, NodeRunStatus.RUNNING, NodeRunStatus.WAITING_EXTERNAL}:
                transition(node_id, NodeRunStatus.CANCELLED, error_code="RUN_CANCELLED")
        run_status = "CANCELLED"
    else:
        successful = sum(
            status in {NodeRunStatus.SUCCEEDED, NodeRunStatus.CACHED, NodeRunStatus.RESTORED}
            for status in states.values()
        )
        failures = any(status in {NodeRunStatus.FAILED, NodeRunStatus.BLOCKED} for status in states.values())
        if failures and successful:
            run_status = "PARTIALLY_SUCCEEDED"
        elif failures:
            run_status = "FAILED"
        else:
            run_status = "SUCCEEDED"

    return {
        "status": run_status,
        "node_runs": [
            {
                "node_id": node_id,
                "status": states[node_id].value,
                "error_code": errors.get(node_id),
                "output": outputs.get(node_id),
            }
            for node_id in node_order
        ],
        "events": event_log,
    }
