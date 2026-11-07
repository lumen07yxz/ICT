"""Compile editable workflow documents into deterministic execution plans."""

from __future__ import annotations

import hashlib
import heapq
import json
from collections import defaultdict, deque
from typing import Any

from app.services.workflow_catalog import (
    WORKFLOW_SCHEMA_VERSION,
    validate_workflow_component_contracts,
    validate_workflow_graph,
)
from app.services.workflow_components import get_workflow_component


EXECUTION_PLAN_SCHEMA_VERSION = "ict.execution.v1"


class WorkflowCompilationError(ValueError):
    """A stable, user-safe workflow compilation failure."""

    def __init__(self, code: str, message: str, *, issues: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.code = code
        self.issues = issues or []


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _topological_order(node_ids: set[str], edges: list[dict[str, Any]]) -> list[str]:
    """Return a stable Kahn order, choosing the smallest ready node ID first."""
    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree = {node_id: 0 for node_id in node_ids}
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        adjacency[source].append(target)
        indegree[target] += 1

    ready = [node_id for node_id, count in indegree.items() if count == 0]
    heapq.heapify(ready)
    ordered: list[str] = []
    while ready:
        source = heapq.heappop(ready)
        ordered.append(source)
        for target in sorted(adjacency[source]):
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(ready, target)

    if len(ordered) != len(node_ids):
        raise WorkflowCompilationError(
            "CYCLE_UNSUPPORTED",
            "当前执行计划不支持循环依赖。",
            issues=[{"code": "CYCLE_UNSUPPORTED"}],
        )
    return ordered


def _raise_first_issue(issues: list[dict[str, Any]]) -> None:
    if issues:
        first = issues[0]
        raise WorkflowCompilationError(
            str(first["code"]),
            str(first.get("message") or "工作流无法编译。"),
            issues=issues,
        )


def compile_execution_plan(
    graph: dict[str, Any],
    *,
    target_node_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Compile the selected output closure without carrying editor-only layout.

    The component registry is the source of truth for each resolved component
    contract. Runtime availability is recorded in the plan but enforced by the
    run admission step, allowing callers to inspect a valid plan before dispatch.
    """
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list) or not isinstance(graph.get("edges"), list):
        raise WorkflowCompilationError("GRAPH_DOCUMENT_INVALID", "工作流图文档格式无效。")

    raw_nodes = graph["nodes"]
    raw_edges = graph["edges"]
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for node in raw_nodes:
        node_id = node.get("id") if isinstance(node, dict) else None
        if not isinstance(node_id, str) or not node_id:
            raise WorkflowCompilationError("NODE_ID_INVALID", "节点缺少有效标识。")
        if node_id in nodes_by_id:
            raise WorkflowCompilationError(
                "DUPLICATE_NODE_ID", "节点 ID 重复。", issues=[{"code": "DUPLICATE_NODE_ID", "node_id": node_id}]
            )
        nodes_by_id[node_id] = node

    if not nodes_by_id:
        raise WorkflowCompilationError("EMPTY_GRAPH", "工作流至少需要一个节点才能编译。")

    edge_ids: set[str] = set()
    normalized_edges: list[dict[str, Any]] = []
    parents: dict[str, list[str]] = defaultdict(list)
    outgoing: set[str] = set()
    for edge in raw_edges:
        if not isinstance(edge, dict):
            raise WorkflowCompilationError("EDGE_INVALID", "工作流包含无效连线。")
        edge_id = edge.get("id")
        source = edge.get("source")
        target = edge.get("target")
        if not isinstance(edge_id, str) or not edge_id or not isinstance(source, str) or not isinstance(target, str):
            raise WorkflowCompilationError("EDGE_INVALID", "连线缺少有效标识或端点。")
        if edge_id in edge_ids:
            raise WorkflowCompilationError(
                "DUPLICATE_EDGE_ID", "连线 ID 重复。", issues=[{"code": "DUPLICATE_EDGE_ID", "edge_id": edge_id}]
            )
        edge_ids.add(edge_id)
        if source not in nodes_by_id or target not in nodes_by_id:
            raise WorkflowCompilationError(
                "EDGE_ENDPOINT_MISSING",
                "连线端点节点不存在。",
                issues=[{"code": "EDGE_ENDPOINT_MISSING", "edge_id": edge_id}],
            )
        normalized = {
            "id": edge_id,
            "source": source,
            "target": target,
            "source_handle": edge.get("sourceHandle", edge.get("source_handle")),
            "target_handle": edge.get("targetHandle", edge.get("target_handle")),
        }
        normalized_edges.append(normalized)
        parents[target].append(source)
        outgoing.add(source)

    if target_node_ids is None:
        targets = sorted(set(nodes_by_id) - outgoing)
        if not targets:
            raise WorkflowCompilationError("NO_OUTPUT_TARGETS", "工作流没有可选择的输出节点。")
    else:
        if not isinstance(target_node_ids, list) or not target_node_ids:
            raise WorkflowCompilationError("TARGETS_REQUIRED", "至少选择一个输出节点。")
        if any(not isinstance(node_id, str) or not node_id for node_id in target_node_ids):
            raise WorkflowCompilationError("TARGET_NODE_ID_INVALID", "输出节点标识无效。")
        targets = sorted(set(target_node_ids))
        missing_targets = [node_id for node_id in targets if node_id not in nodes_by_id]
        if missing_targets:
            raise WorkflowCompilationError(
                "TARGET_NODE_NOT_FOUND",
                "选择的输出节点不存在。",
                issues=[{"code": "TARGET_NODE_NOT_FOUND", "node_id": node_id} for node_id in missing_targets],
            )

    # Walk backwards from requested outputs so independent branches are omitted.
    selected_ids: set[str] = set()
    pending = deque(targets)
    while pending:
        node_id = pending.popleft()
        if node_id in selected_ids:
            continue
        selected_ids.add(node_id)
        pending.extend(parents[node_id])

    selected_nodes = [nodes_by_id[node_id] for node_id in sorted(selected_ids)]
    selected_edges = [
        edge for edge in normalized_edges
        if edge["source"] in selected_ids and edge["target"] in selected_ids
    ]
    selected_graph = {
        "schema_version": graph.get("schema_version", WORKFLOW_SCHEMA_VERSION),
        "nodes": selected_nodes,
        "edges": [
            {
                "id": edge["id"],
                "source": edge["source"],
                "target": edge["target"],
                "sourceHandle": edge["source_handle"],
                "targetHandle": edge["target_handle"],
            }
            for edge in selected_edges
        ],
    }
    _raise_first_issue(validate_workflow_graph(selected_graph))
    _raise_first_issue(validate_workflow_component_contracts(selected_graph))

    node_order = _topological_order(selected_ids, selected_edges)
    resolved_nodes: list[dict[str, Any]] = []
    for node_id in node_order:
        data = nodes_by_id[node_id].get("data")
        if not isinstance(data, dict):
            data = {}
        component_id = data.get("component_id")
        component = get_workflow_component(component_id) if isinstance(component_id, str) else None
        # Contract validation above guarantees that the selected component resolves.
        if component is None:
            raise WorkflowCompilationError(
                "COMPONENT_NOT_REGISTERED",
                "节点组件未登记，无法生成执行计划。",
                issues=[{"code": "COMPONENT_NOT_REGISTERED", "node_id": node_id}],
            )
        contract = {
            "schema_version": component["schema_version"],
            "component_id": component["component_id"],
            "version": component["version"],
            "inputs": component["inputs"],
            "outputs": component["outputs"],
            "parameter_schema": component["parameter_schema"],
            "executor_binding": component["executor_binding"],
            "executor_version": component["executor_version"],
            "implementation_digest": component["implementation_digest"],
            "execution_target": component["execution_target"],
            "dependencies": component["dependencies"],
            "permissions": component["permissions"],
            "resource_limits": component["resource_limits"],
            "cache_policy": component["cache_policy"],
        }
        contract_hash = hashlib.sha256(_canonical_json(contract).encode("utf-8")).hexdigest()
        resolved_nodes.append(
            {
                "id": node_id,
                "component_id": component["component_id"],
                "component_version": component["version"],
                "component_schema_version": component["schema_version"],
                "component_contract_hash": contract_hash,
                "parameters": data.get("parameters", {}),
                "executor_binding": component["executor_binding"],
                "executor_version": component["executor_version"],
                "implementation_digest": component["implementation_digest"],
                "execution_target": component["execution_target"],
                "dependencies": component["dependencies"],
                "permissions": component["permissions"],
                "resource_limits": component["resource_limits"],
                "cache_policy": component["cache_policy"],
            }
        )

    plan_body = {
        "schema_version": EXECUTION_PLAN_SCHEMA_VERSION,
        "workflow_schema_version": graph.get("schema_version", WORKFLOW_SCHEMA_VERSION),
        "target_node_ids": targets,
        "node_order": node_order,
        "nodes": resolved_nodes,
        "edges": sorted(
            selected_edges,
            key=lambda edge: (
                edge["target"], edge["target_handle"] or "", edge["source"],
                edge["source_handle"] or "", edge["id"],
            ),
        ),
    }
    try:
        plan_hash = hashlib.sha256(_canonical_json(plan_body).encode("utf-8")).hexdigest()
    except (TypeError, ValueError) as error:
        raise WorkflowCompilationError("PLAN_VALUE_NOT_SERIALIZABLE", "工作流参数包含无法序列化的值。") from error
    return {**plan_body, "plan_hash": plan_hash}
