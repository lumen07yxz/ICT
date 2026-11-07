"""Versioned, offline workflow templates shipped with the local runtime."""

from __future__ import annotations

from copy import deepcopy
from math import isfinite
from uuid import uuid4


CSV_EXPLORATION_TEMPLATE_ID = "ict.local.csv_quality_exploration"
CSV_EXPLORATION_TEMPLATE_VERSION = "1.0.0"
CSV_FOLDER_QUALITY_TEMPLATE_ID = "ict.local.csv_folder_quality"
CSV_FOLDER_QUALITY_TEMPLATE_VERSION = "1.0.0"

_CSV_EXPLORATION_TEMPLATE = {
    "template_id": CSV_EXPLORATION_TEMPLATE_ID,
    "version": CSV_EXPLORATION_TEMPLATE_VERSION,
    "name": "CSV 结构预检与描述统计",
    "category": "数据检验",
    "summary": "在本机选择 CSV 字段，并生成结构预检和探索性描述统计报告。",
    "description": (
        "使用本机 CSV 产物完成字段选择、结构预检和描述统计。文件不会上传；"
        "结构检查和描述统计均不构成科研结果或实验准确性结论。"
    ),
    "component_ids": [
        "ict.data.csv_artifact_source",
        "ict.data.csv_select_columns",
        "ict.data.csv_manifest_preflight_input",
        "ict.data.csv_descriptive_summary",
    ],
    "execution_target": "local",
    "requires_network": False,
}

_CSV_FOLDER_QUALITY_TEMPLATE = {
    "template_id": CSV_FOLDER_QUALITY_TEMPLATE_ID,
    "version": CSV_FOLDER_QUALITY_TEMPLATE_VERSION,
    "name": "CSV 文件夹逐文件质量检查",
    "category": "数据检验",
    "summary": "递归选择本机文件夹，对其中 CSV 逐个检查并生成汇总报告。",
    "description": (
        "只处理用户选定目录中的 CSV 文件，支持子目录；其他文件会明确跳过。"
        "数据只保存在本机，报告列出每个文件的检查状态，不构成科研结果。"
    ),
    "component_ids": ["ict.data.csv_folder_source", "ict.data.quality_check"],
    "execution_target": "local",
    "requires_network": False,
}


def list_local_workflow_templates() -> list[dict[str, object]]:
    """Return metadata plus a sanitized topology preview derived from each graph factory."""
    templates = [deepcopy(_CSV_EXPLORATION_TEMPLATE), deepcopy(_CSV_FOLDER_QUALITY_TEMPLATE)]
    for template in templates:
        graph = instantiate_local_workflow_template(str(template["template_id"]), str(template["version"]))
        if graph is None:
            continue
        preview = _workflow_preview_from_graph(graph)
        if preview is not None:
            template["workflow_preview"] = preview
    return templates


def instantiate_local_workflow_template(template_id: str, version: str) -> dict[str, object] | None:
    """Build a fresh typed graph only for a template shipped in this runtime."""
    if template_id == CSV_FOLDER_QUALITY_TEMPLATE_ID and version == CSV_FOLDER_QUALITY_TEMPLATE_VERSION:
        suffix = uuid4().hex
        source_id = f"csv-folder-source-{suffix}"
        check_id = f"csv-folder-quality-{suffix}"
        nodes = [
            {
                "id": source_id,
                "type": "research",
                "position": {"x": 80, "y": 210},
                "data": {
                    "category": "数据输入",
                    "title": "本机 CSV 文件夹",
                    "description": "递归选择文件夹并导入其中的 CSV；文件不会上传。",
                    "component_id": "ict.data.csv_folder_source",
                    "component_version": "1.0.0",
                    "parameters": {"files_json": ""},
                },
            },
            {
                "id": check_id,
                "type": "research",
                "position": {"x": 510, "y": 210},
                "data": {
                    "category": "数据检验",
                    "title": "CSV 文件夹质量检查",
                    "description": "逐文件检查字段、缺失率和配置的唯一键，保存汇总报告。",
                    "component_id": "ict.data.quality_check",
                    "component_version": "2.0.0",
                    "parameters": {
                        "required_columns": "",
                        "unique_key_columns": "",
                        "max_missing_rate": "0.05",
                    },
                },
            },
        ]
        edges = [{
            "id": f"edge-csv-folder-quality-{suffix}",
            "source": source_id,
            "sourceHandle": "out:files",
            "target": check_id,
            "targetHandle": "in:files",
            "type": "smoothstep",
        }]
        return {"schema_version": "ict.workflow.v1", "nodes": nodes, "edges": edges}

    if template_id != CSV_EXPLORATION_TEMPLATE_ID or version != CSV_EXPLORATION_TEMPLATE_VERSION:
        return None

    suffix = uuid4().hex
    source_id = f"csv-source-{suffix}"
    select_id = f"csv-select-{suffix}"
    preflight_id = f"csv-preflight-{suffix}"
    summary_id = f"csv-summary-{suffix}"

    nodes = [
        {
            "id": source_id,
            "type": "research",
            "position": {"x": 40, "y": 230},
            "data": {
                "category": "数据输入",
                "title": "本机 CSV 数据输入",
                "description": "从本机已授权产物库读取 CSV；运行前请导入文件。",
                "component_id": "ict.data.csv_artifact_source",
                "component_version": "1.0.0",
                "parameters": {"artifact_id": ""},
            },
        },
        {
            "id": select_id,
            "type": "research",
            "position": {"x": 390, "y": 230},
            "data": {
                "category": "数据处理",
                "title": "CSV 字段选择",
                "description": "填写要保留的字段名，英文逗号分隔。",
                "component_id": "ict.data.csv_select_columns",
                "component_version": "1.0.0",
                "parameters": {"columns": ""},
            },
        },
        {
            "id": preflight_id,
            "type": "research",
            "position": {"x": 790, "y": 105},
            "data": {
                "category": "数据检验",
                "title": "CSV 结构预检",
                "description": "检查通用字段、重复记录和分组拆分结构；报告不是科研结果。",
                "component_id": "ict.data.csv_manifest_preflight_input",
                "component_version": "1.0.0",
                "parameters": {},
            },
        },
        {
            "id": summary_id,
            "type": "research",
            "position": {"x": 790, "y": 390},
            "data": {
                "category": "数据检验",
                "title": "CSV 描述统计摘要",
                "description": "汇总字段缺失率、数值范围与类别频数；仅作探索性摘要。",
                "component_id": "ict.data.csv_descriptive_summary",
                "component_version": "1.0.0",
                "parameters": {},
            },
        },
    ]
    edges = [
        {
            "id": f"edge-source-select-{suffix}",
            "source": source_id,
            "sourceHandle": "out:csv",
            "target": select_id,
            "targetHandle": "in:csv",
            "type": "smoothstep",
        },
        {
            "id": f"edge-select-preflight-{suffix}",
            "source": select_id,
            "sourceHandle": "out:selected_csv",
            "target": preflight_id,
            "targetHandle": "in:csv",
            "type": "smoothstep",
        },
        {
            "id": f"edge-select-summary-{suffix}",
            "source": select_id,
            "sourceHandle": "out:selected_csv",
            "target": summary_id,
            "targetHandle": "in:csv",
            "type": "smoothstep",
        },
    ]
    return {"schema_version": "ict.workflow.v1", "nodes": nodes, "edges": edges}


def _workflow_preview_from_graph(graph: dict[str, object]) -> dict[str, object] | None:
    """Expose only stable node labels and links; do not leak per-instance IDs or parameters."""
    graph_nodes = graph.get("nodes")
    graph_edges = graph.get("edges")
    if not isinstance(graph_nodes, list) or not isinstance(graph_edges, list):
        return None

    # Template instances use random IDs; stable preview IDs keep catalog responses deterministic.
    preview_id_by_graph_id: dict[str, str] = {}
    preview_nodes: list[dict[str, object]] = []
    for index, node in enumerate(graph_nodes):
        if not isinstance(node, dict):
            return None
        graph_id = node.get("id")
        data = node.get("data")
        position = node.get("position")
        if not isinstance(graph_id, str) or graph_id in preview_id_by_graph_id:
            return None
        if not isinstance(data, dict) or not isinstance(position, dict):
            return None

        title = data.get("title")
        category = data.get("category")
        x = position.get("x")
        y = position.get("y")
        if not isinstance(title, str) or not isinstance(category, str):
            return None
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(float(x)):
            return None
        if isinstance(y, bool) or not isinstance(y, (int, float)) or not isfinite(float(y)):
            return None

        preview_id = f"node-{index + 1}"
        preview_id_by_graph_id[graph_id] = preview_id
        preview_nodes.append({
            "id": preview_id,
            "title": title,
            "category": category,
            "position": {"x": float(x), "y": float(y)},
        })

    preview_edges: list[dict[str, object]] = []
    for edge in graph_edges:
        if not isinstance(edge, dict):
            return None
        source = edge.get("source")
        target = edge.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            return None
        if source not in preview_id_by_graph_id or target not in preview_id_by_graph_id:
            return None
        preview_edges.append({
            "source": preview_id_by_graph_id[source],
            "target": preview_id_by_graph_id[target],
        })

    return {"nodes": preview_nodes, "edges": preview_edges}
