"""Project- and reproduction-task-scoped workflow access and graph validation."""

from collections import defaultdict, deque
from copy import deepcopy
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import DemoIdentity
from app.db.models import (
    Membership,
    Project,
    ReproductionTask,
    Workflow,
    WorkflowVersion,
    WorkspaceMembership,
)
from app.errors import AppError
from app.services.workflow_components import get_workflow_component


WORKFLOW_SCHEMA_VERSION = "ict.workflow.v1"
EMPTY_WORKFLOW_GRAPH: dict[str, Any] = {
    "schema_version": WORKFLOW_SCHEMA_VERSION,
    "nodes": [],
    "edges": [],
}


def _project_membership(
    session: Session, identity: DemoIdentity, project_id: UUID
) -> tuple[Project, str]:
    """Hide absent and unauthorized projects behind one response code."""
    row = session.execute(
        select(Project, Membership.role)
        .join(Membership, Membership.project_id == Project.id)
        .where(Project.id == project_id, Membership.user_id == identity.user_id)
    ).one_or_none()
    if row is None or row[0].visibility != "private":
        raise AppError(404, "PROJECT_NOT_FOUND")
    return row[0], row[1]


def _require_operator(identity: DemoIdentity, membership_role: str) -> None:
    if identity.role != "operator" or membership_role != "operator":
        raise AppError(403, "OPERATOR_REQUIRED")


def list_project_workflows(
    session: Session, identity: DemoIdentity, project_id: UUID
) -> list[Workflow]:
    """Return only workflows inside a project the caller can access."""
    _project_membership(session, identity, project_id)
    rows = session.scalars(
        select(Workflow)
        .where(Workflow.project_id == project_id)
        .order_by(Workflow.updated_at.desc(), Workflow.id)
    )
    return list(rows)


def create_project_workflow(
    session: Session,
    identity: DemoIdentity,
    project_id: UUID,
    *,
    name: str,
    description: str,
) -> Workflow:
    """Create a persistent draft whose project ownership is enforced by a foreign key."""
    project, membership_role = _project_membership(session, identity, project_id)
    _require_operator(identity, membership_role)
    workflow = Workflow(
        id=uuid4(),
        workspace_id=project.workspace_id,
        owner_type="project",
        project_id=project_id,
        name=name,
        description=description,
        graph=EMPTY_WORKFLOW_GRAPH,
        revision=1,
        current_version=0,
        created_by=identity.user_id,
        updated_by=identity.user_id,
    )
    session.add(workflow)
    session.commit()
    session.refresh(workflow)
    return workflow


def _reproduction_membership(
    session: Session, identity: DemoIdentity, task_id: UUID
) -> tuple[ReproductionTask, str]:
    """Hide absent and unauthorized reproduction tasks behind one response code."""
    row = session.execute(
        select(ReproductionTask, WorkspaceMembership.role)
        .join(
            WorkspaceMembership,
            WorkspaceMembership.workspace_id == ReproductionTask.workspace_id,
        )
        .where(
            ReproductionTask.id == task_id,
            WorkspaceMembership.user_id == identity.user_id,
        )
    ).one_or_none()
    if row is None:
        raise AppError(404, "REPRODUCTION_TASK_NOT_FOUND")
    return row[0], row[1]


def list_reproduction_workflows(
    session: Session, identity: DemoIdentity, task_id: UUID
) -> list[Workflow]:
    """Return only workflows owned by a reproduction task in the caller's workspace."""
    _reproduction_membership(session, identity, task_id)
    rows = session.scalars(
        select(Workflow)
        .where(Workflow.reproduction_task_id == task_id)
        .order_by(Workflow.updated_at.desc(), Workflow.id)
    )
    return list(rows)


def create_reproduction_workflow(
    session: Session,
    identity: DemoIdentity,
    task_id: UUID,
    *,
    name: str,
    description: str,
) -> Workflow:
    """Create a persistent draft owned by the task and its isolation workspace."""
    task, membership_role = _reproduction_membership(session, identity, task_id)
    _require_operator(identity, membership_role)
    workflow = Workflow(
        id=uuid4(),
        workspace_id=task.workspace_id,
        owner_type="reproduction",
        reproduction_task_id=task_id,
        name=name,
        description=description,
        graph=EMPTY_WORKFLOW_GRAPH,
        revision=1,
        current_version=0,
        created_by=identity.user_id,
        updated_by=identity.user_id,
    )
    session.add(workflow)
    session.commit()
    session.refresh(workflow)
    return workflow


def get_visible_workflow(
    session: Session,
    identity: DemoIdentity,
    workflow_id: UUID,
    *,
    for_update: bool = False,
) -> tuple[Workflow, str]:
    """Load a workflow through the membership of its single owning object."""
    statement = select(Workflow).where(Workflow.id == workflow_id)
    if for_update:
        statement = statement.with_for_update()
    workflow = session.scalar(statement)
    if workflow is None:
        raise AppError(404, "WORKFLOW_NOT_FOUND")

    if workflow.owner_type == "project" and workflow.project_id is not None:
        try:
            project, role = _project_membership(session, identity, workflow.project_id)
        except AppError as error:
            raise AppError(404, "WORKFLOW_NOT_FOUND") from error
        if project.visibility != "private":
            raise AppError(404, "WORKFLOW_NOT_FOUND")
        return workflow, role
    if workflow.owner_type == "reproduction" and workflow.reproduction_task_id is not None:
        try:
            _task, role = _reproduction_membership(
                session, identity, workflow.reproduction_task_id
            )
        except AppError as error:
            raise AppError(404, "WORKFLOW_NOT_FOUND") from error
        return workflow, role
    raise AppError(404, "WORKFLOW_NOT_FOUND")


def update_workflow_draft(
    session: Session,
    identity: DemoIdentity,
    workflow_id: UUID,
    *,
    expected_revision: int,
    name: str,
    description: str,
    graph: dict[str, Any],
) -> Workflow:
    """Apply one optimistic-concurrency draft update without mutating old snapshots."""
    workflow, membership_role = get_visible_workflow(
        session, identity, workflow_id, for_update=True
    )
    _require_operator(identity, membership_role)
    if workflow.revision != expected_revision:
        raise AppError(409, "WORKFLOW_REVISION_CONFLICT")

    workflow.name = name
    workflow.description = description
    workflow.graph = graph
    workflow.revision += 1
    workflow.updated_by = identity.user_id
    session.commit()
    session.refresh(workflow)
    return workflow


def restore_workflow_version_draft(
    session: Session,
    identity: DemoIdentity,
    workflow_id: UUID,
    version_number: int,
    *,
    expected_revision: int,
) -> Workflow:
    """Copy an immutable snapshot into the draft without changing version history."""
    workflow, membership_role = get_visible_workflow(
        session, identity, workflow_id, for_update=True
    )
    _require_operator(identity, membership_role)
    if workflow.revision != expected_revision:
        raise AppError(409, "WORKFLOW_REVISION_CONFLICT")

    version = session.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow.id,
            WorkflowVersion.version == version_number,
        )
    )
    if version is None:
        raise AppError(404, "WORKFLOW_VERSION_NOT_FOUND")

    # Legacy graph-only snapshots retain the current draft metadata on restore.
    if version.name is not None:
        workflow.name = version.name
    if version.description is not None:
        workflow.description = version.description
    workflow.graph = deepcopy(version.graph)
    workflow.revision += 1
    workflow.updated_by = identity.user_id
    session.commit()
    session.refresh(workflow)
    return workflow


def validate_workflow_graph(graph: dict[str, Any]) -> list[dict[str, str | None]]:
    """Check graph structure only; component contracts and execution are separate gates."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    issues: list[dict[str, str | None]] = []

    def issue(code: str, message: str, *, node_id: str | None = None, edge_id: str | None = None) -> None:
        issues.append({"code": code, "message": message, "node_id": node_id, "edge_id": edge_id})

    if not nodes:
        issue("EMPTY_GRAPH", "工作流至少需要一个节点才能创建版本。")

    node_ids: set[str] = set()
    for node in nodes:
        node_id = node["id"]
        if node_id in node_ids:
            issue("DUPLICATE_NODE_ID", "节点 ID 重复。", node_id=node_id)
        node_ids.add(node_id)

    edge_ids: set[str] = set()
    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree = {node_id: 0 for node_id in node_ids}
    for edge in edges:
        edge_id = edge["id"]
        source = edge["source"]
        target = edge["target"]
        if edge_id in edge_ids:
            issue("DUPLICATE_EDGE_ID", "连线 ID 重复。", edge_id=edge_id)
        edge_ids.add(edge_id)
        if source not in node_ids:
            issue("EDGE_SOURCE_MISSING", "连线的起点节点不存在。", edge_id=edge_id)
        if target not in node_ids:
            issue("EDGE_TARGET_MISSING", "连线的终点节点不存在。", edge_id=edge_id)
        if source == target and source in node_ids:
            issue("SELF_CONNECTION", "节点不能直接连接到自身。", node_id=source, edge_id=edge_id)
        if source in node_ids and target in node_ids and source != target:
            adjacency[source].append(target)
            indegree[target] += 1

    ready = deque(node_id for node_id, count in indegree.items() if count == 0)
    visited = 0
    while ready:
        source = ready.popleft()
        visited += 1
        for target in adjacency[source]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    if node_ids and visited != len(node_ids):
        issue("CYCLE_UNSUPPORTED", "当前首版不支持循环依赖；请移除形成环路的连线。")

    return issues


def validate_workflow_component_contracts(
    graph: dict[str, Any],
) -> list[dict[str, str | None]]:
    """Check registered node versions, parameters, required ports, and port types."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    issues: list[dict[str, str | None]] = []
    definitions: dict[str, dict[str, Any]] = {}
    components: dict[str, dict[str, Any] | None] = {}
    connected_inputs: set[tuple[str, str]] = set()
    input_connection_counts: dict[tuple[str, str], int] = defaultdict(int)

    def issue(
        code: str,
        message: str,
        *,
        node_id: str | None = None,
        edge_id: str | None = None,
    ) -> None:
        issues.append({"code": code, "message": message, "node_id": node_id, "edge_id": edge_id})

    for node in nodes:
        node_id = node["id"]
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        component_id = data.get("component_id")
        if not isinstance(component_id, str) or not component_id:
            issue("COMPONENT_ID_REQUIRED", "节点缺少已登记的组件类型。", node_id=node_id)
            components[node_id] = None
            continue

        component = get_workflow_component(component_id)
        if component is None:
            issue("COMPONENT_NOT_REGISTERED", "节点引用的组件未在当前注册表中登记。", node_id=node_id)
            components[node_id] = None
            continue

        components[node_id] = component
        definitions[node_id] = component
        if data.get("component_version") != component["version"]:
            issue("COMPONENT_VERSION_UNAVAILABLE", "节点组件版本与当前注册表版本不匹配。", node_id=node_id)

        parameter_schema = component["parameter_schema"]
        properties = parameter_schema["properties"]
        parameters = data.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}
        for unknown_key in parameters.keys() - properties.keys():
            issue(
                "PARAMETER_NOT_REGISTERED",
                "节点包含当前组件契约未登记的参数。",
                node_id=node_id,
            )
        for key, property_schema in properties.items():
            value = parameters.get(key)
            required = key in parameter_schema["required"]
            empty = value is None or (isinstance(value, str) and not value.strip())
            if required and empty:
                issue(
                    "PARAMETER_REQUIRED",
                    f"请填写参数“{property_schema['title']}”。",
                    node_id=node_id,
                )
            elif value is not None and property_schema["type"] == "string" and not isinstance(value, str):
                issue(
                    "PARAMETER_TYPE_INVALID",
                    f"参数“{property_schema['title']}”必须是文本。",
                    node_id=node_id,
                )
            elif property_schema["type"] == "string" and isinstance(value, str):
                # Enforce declared string bounds during compilation, before any executor runs.
                min_length = property_schema.get("minLength")
                max_length = property_schema.get("maxLength")
                if type(min_length) is int and len(value) < min_length:
                    issue(
                        "PARAMETER_MIN_LENGTH_UNSATISFIED",
                        f"参数“{property_schema['title']}”长度不得少于 {min_length} 个字符。",
                        node_id=node_id,
                    )
                if type(max_length) is int and len(value) > max_length:
                    issue(
                        "PARAMETER_MAX_LENGTH_EXCEEDED",
                        f"参数“{property_schema['title']}”长度不得超过 {max_length} 个字符。",
                        node_id=node_id,
                    )

    for edge in edges:
        edge_id = edge["id"]
        source_id = edge["source"]
        target_id = edge["target"]
        source_component = components.get(source_id)
        target_component = components.get(target_id)
        if source_component is None or target_component is None:
            continue

        source_handle = edge.get("sourceHandle") or edge.get("source_handle")
        target_handle = edge.get("targetHandle") or edge.get("target_handle")
        source_port_id = source_handle.removeprefix("out:") if isinstance(source_handle, str) and source_handle.startswith("out:") else None
        target_port_id = target_handle.removeprefix("in:") if isinstance(target_handle, str) and target_handle.startswith("in:") else None
        source_ports = {port["id"]: port for port in source_component["outputs"]}
        target_ports = {port["id"]: port for port in target_component["inputs"]}
        source_port = source_ports.get(source_port_id) if source_port_id else None
        target_port = target_ports.get(target_port_id) if target_port_id else None

        if source_handle is None:
            issue("SOURCE_PORT_REQUIRED", "连线必须指定来源输出端口。", edge_id=edge_id)
        elif source_port is None:
            issue("SOURCE_PORT_UNKNOWN", "连线引用了不存在的输出端口。", edge_id=edge_id)
        if target_handle is None:
            issue("TARGET_PORT_REQUIRED", "连线必须指定目标输入端口。", edge_id=edge_id)
        elif target_port is None:
            issue("TARGET_PORT_UNKNOWN", "连线引用了不存在的输入端口。", edge_id=edge_id)

        if source_port is None or target_port is None:
            continue
        input_key = (target_id, target_port["id"])
        input_connection_counts[input_key] += 1
        connected_inputs.add(input_key)
        if source_port["data_type"] != target_port["data_type"]:
            issue(
                "PORT_TYPE_MISMATCH",
                f"输出类型 {source_port['data_type']} 与输入类型 {target_port['data_type']} 不兼容。",
                edge_id=edge_id,
            )

    for node_id, component in definitions.items():
        for port in component["inputs"]:
            key = (node_id, port["id"])
            count = input_connection_counts[key]
            if port["required"] and key not in connected_inputs:
                issue(
                    "REQUIRED_INPUT_UNCONNECTED",
                    f"必需输入“{port['label']}”尚未连接。",
                    node_id=node_id,
                )
            if not port["multiple"] and count > 1:
                issue(
                    "INPUT_CONNECTION_LIMIT",
                    f"输入“{port['label']}”只能连接一个来源。",
                    node_id=node_id,
                )

    return issues


def create_workflow_version(
    session: Session, identity: DemoIdentity, workflow_id: UUID
) -> tuple[Workflow, WorkflowVersion, bool]:
    """Create an immutable snapshot; repeating the latest unchanged request is idempotent."""
    workflow, membership_role = get_visible_workflow(
        session, identity, workflow_id, for_update=True
    )
    _require_operator(identity, membership_role)
    issues = validate_workflow_graph(workflow.graph) + validate_workflow_component_contracts(workflow.graph)
    if issues:
        raise AppError(422, "WORKFLOW_VALIDATION_BLOCKED")

    latest = session.scalar(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow.id)
        .order_by(WorkflowVersion.version.desc())
        .limit(1)
    )
    content_hash = _workflow_content_hash(workflow.name, workflow.description, workflow.graph)
    if latest is not None and latest.content_hash == content_hash:
        return workflow, latest, False

    version = WorkflowVersion(
        id=uuid4(),
        workflow_id=workflow.id,
        version=workflow.current_version + 1,
        name=workflow.name,
        description=workflow.description,
        graph=workflow.graph,
        schema_version=str(workflow.graph.get("schema_version", WORKFLOW_SCHEMA_VERSION)),
        content_hash=content_hash,
        created_by=identity.user_id,
    )
    workflow.current_version = version.version
    session.add(version)
    session.commit()
    session.refresh(workflow)
    session.refresh(version)
    return workflow, version, True


def _workflow_content_hash(name: str, description: str, graph: dict[str, Any]) -> str:
    """Hash normalized workflow metadata and graph as one immutable snapshot."""
    import hashlib
    import json

    canonical = json.dumps(
        {"name": name, "description": description, "graph": graph},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
