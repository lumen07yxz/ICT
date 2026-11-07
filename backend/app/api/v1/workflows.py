"""Persistent project workflow drafts and immutable version snapshots."""

import logging
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from app.api.dependencies import get_database_session
from app.auth import DemoIdentity, get_demo_identity
from app.db.models import Workflow, WorkflowVersion
from app.errors import AppError
from app.services.workflow_catalog import (
    WORKFLOW_SCHEMA_VERSION,
    create_project_workflow,
    create_reproduction_workflow,
    create_workflow_version,
    get_visible_workflow,
    list_project_workflows,
    list_reproduction_workflows,
    restore_workflow_version_draft,
    update_workflow_draft,
    validate_workflow_component_contracts,
    validate_workflow_graph,
)
from app.services.workflow_components import list_workflow_components


logger = logging.getLogger("ict.workflow")
router = APIRouter(tags=["workflows"])


class NodePosition(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    x: float = Field(ge=-1_000_000, le=1_000_000)
    y: float = Field(ge=-1_000_000, le=1_000_000)


class WorkflowNodeDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=128)
    type: str = Field(min_length=1, max_length=80)
    position: NodePosition
    data: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdgeDocument(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=128)
    source_handle: str | None = Field(default=None, alias="sourceHandle", max_length=128)
    target_handle: str | None = Field(default=None, alias="targetHandle", max_length=128)
    type: str | None = Field(default=None, max_length=80)


class WorkflowGraphDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ict.workflow.v1"] = WORKFLOW_SCHEMA_VERSION
    nodes: list[WorkflowNodeDocument] = Field(max_length=500)
    edges: list[WorkflowEdgeDocument] = Field(max_length=2_000)

    @model_validator(mode="after")
    def bound_serialized_size(self) -> "WorkflowGraphDocument":
        if len(self.model_dump_json().encode("utf-8")) > 2_000_000:
            raise ValueError("workflow graph exceeds the 2 MB limit")
        return self


class WorkflowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4_000)


class WorkflowUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(max_length=4_000)
    graph: WorkflowGraphDocument


class WorkflowVersionRestore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)


class WorkflowSummaryRead(BaseModel):
    id: UUID
    workspace_id: UUID
    owner_type: Literal["project", "reproduction"]
    owner_id: UUID
    project_id: UUID | None
    reproduction_task_id: UUID | None
    name: str
    description: str
    revision: int
    current_version: int
    created_at: datetime
    updated_at: datetime


class WorkflowRead(WorkflowSummaryRead):
    graph: WorkflowGraphDocument
    can_edit: bool


class WorkflowValidationIssueRead(BaseModel):
    scope: Literal["structure", "component"]
    code: str
    message: str
    severity: Literal["blocker", "warning", "info"]
    title: str
    reason: str
    impact: str
    guidance: str
    node_id: str | None = None
    edge_id: str | None = None


class WorkflowValidationRead(BaseModel):
    workflow_id: UUID
    revision: int
    structural_status: Literal["valid", "invalid"]
    contract_status: Literal["valid", "invalid"]
    executable: Literal[False] = False
    execution_blockers: list[str]
    issues: list[WorkflowValidationIssueRead]


# The current validator emits blocking errors only. Keep copy tied to concrete rule codes;
# warnings and informational findings are added only when the validator has such rules.
_VALIDATION_ISSUE_DETAILS: dict[str, tuple[str, str, str]] = {
    "EMPTY_GRAPH": ("工作流为空", "当前结构校验无法通过，也不能创建有效版本。", "从组件目录添加至少一个节点后重新校验。"),
    "DUPLICATE_NODE_ID": ("节点标识重复", "节点无法被唯一引用，当前工作流版本不能创建。", "删除或重建重复标识的节点后重新校验。"),
    "DUPLICATE_EDGE_ID": ("连线标识重复", "连线无法被唯一引用，当前工作流版本不能创建。", "删除或重建重复标识的连线后重新校验。"),
    "EDGE_SOURCE_MISSING": ("连线起点缺失", "依赖关系没有有效起点，工作流结构校验失败。", "删除失效连线，或重新连接到画布中的来源节点。"),
    "EDGE_TARGET_MISSING": ("连线终点缺失", "依赖关系没有有效终点，工作流结构校验失败。", "删除失效连线，或重新连接到画布中的目标节点。"),
    "SELF_CONNECTION": ("节点自连接", "节点依赖指向自身，当前工作流结构无效。", "移除该自连接，并连接到其他有效节点。"),
    "CYCLE_UNSUPPORTED": ("存在循环依赖", "当前版本不支持循环图，无法创建有效工作流版本。", "调整连线以移除循环依赖，再重新校验。"),
    "COMPONENT_ID_REQUIRED": ("组件类型缺失", "节点没有可校验的组件契约，组件校验无法通过。", "从已登记组件目录为该节点选择组件类型。"),
    "COMPONENT_NOT_REGISTERED": ("组件未登记", "节点引用的组件契约不存在，当前工作流版本不能创建。", "替换为组件目录中已登记的组件类型。"),
    "COMPONENT_VERSION_UNAVAILABLE": ("组件版本不匹配", "当前注册表无法按节点引用的版本解释其参数和端口。", "更新节点到当前登记版本，并检查参数及端口后重新校验。"),
    "PARAMETER_NOT_REGISTERED": ("参数未登记", "组件契约不认识该参数，无法验证其含义和值。", "移除该参数，或先更新组件契约再重新校验。"),
    "PARAMETER_REQUIRED": ("必需参数缺失", "节点参数不完整，组件契约校验失败。", "在右侧属性检查中填写该参数，然后重新校验。"),
    "PARAMETER_TYPE_INVALID": ("参数类型不匹配", "参数值不符合组件契约定义的数据类型。", "按组件契约要求调整参数值类型后重新校验。"),
    "PARAMETER_MIN_LENGTH_UNSATISFIED": ("参数短于最小长度", "参数值未达到组件契约要求的最小长度，无法创建有效版本。", "参照组件契约显示的最小长度限制补足参数，再重新校验。"),
    "PARAMETER_MAX_LENGTH_EXCEEDED": ("参数超过允许长度", "参数值超过组件契约规定的长度，无法创建有效版本。", "参照组件契约显示的最大长度限制缩短参数值，再重新校验。"),
    "SOURCE_PORT_REQUIRED": ("来源端口缺失", "连线没有指定输出端口，数据来源无法确定。", "选择来源节点上已登记的输出端口。"),
    "SOURCE_PORT_UNKNOWN": ("来源端口不存在", "连线引用的输出端口不在来源组件契约中。", "重新选择来源节点上已登记的输出端口。"),
    "TARGET_PORT_REQUIRED": ("目标端口缺失", "连线没有指定输入端口，数据去向无法确定。", "选择目标节点上已登记的输入端口。"),
    "TARGET_PORT_UNKNOWN": ("目标端口不存在", "连线引用的输入端口不在目标组件契约中。", "重新选择目标节点上已登记的输入端口。"),
    "PORT_TYPE_MISMATCH": ("端口数据类型不兼容", "来源输出与目标输入的数据类型不同，不能建立有效依赖。", "将连线接到数据类型一致的输入端口，或调整上游输出。"),
    "REQUIRED_INPUT_UNCONNECTED": ("必需输入未连接", "节点缺少组件契约要求的上游数据，工作流版本不能创建。", "为该输入连接兼容的上游输出端口。"),
    "INPUT_CONNECTION_LIMIT": ("输入连接数量超限", "该输入收到的来源数量超过组件契约限制。", "移除多余连线，使该输入只连接一个来源。"),
}


def _workflow_validation_issue_read(issue: dict[str, Any]) -> WorkflowValidationIssueRead:
    """Attach actionable copy to a known rule without changing its validation meaning."""
    title, impact, guidance = _VALIDATION_ISSUE_DETAILS.get(
        issue["code"],
        ("工作流校验未通过", "该问题阻止当前工作流创建有效版本。", "按校验信息修正关联对象后重新校验。"),
    )
    return WorkflowValidationIssueRead(
        **issue,
        severity="blocker",
        title=title,
        reason=issue["message"],
        impact=impact,
        guidance=guidance,
    )


class WorkflowPortRead(BaseModel):
    id: str
    label: str
    data_type: str
    required: bool
    multiple: bool


class WorkflowComponentRead(BaseModel):
    schema_version: str
    component_id: str
    version: str
    category: str
    title: str
    description: str
    inputs: list[WorkflowPortRead]
    outputs: list[WorkflowPortRead]
    parameter_schema: dict[str, Any]
    executor_binding: str | None
    executor_version: str | None
    implementation_digest: str | None
    execution_target: Literal["local", "network", "platform"]
    dependencies: list[str]
    permissions: list[str]
    resource_limits: dict[str, int | None]
    cache_policy: str
    error_types: list[str]
    execution_available: bool


class WorkflowVersionSummaryRead(BaseModel):
    id: UUID
    workflow_id: UUID
    version: int
    name: str | None = None
    description: str | None = None
    schema_version: str
    content_hash: str
    created_by: str
    created_at: datetime


class WorkflowVersionRead(WorkflowVersionSummaryRead):
    graph: WorkflowGraphDocument


class WorkflowVersionCreatedRead(BaseModel):
    created: bool
    workflow: WorkflowSummaryRead
    version: WorkflowVersionSummaryRead


def _graph_read(graph: dict[str, Any]) -> WorkflowGraphDocument:
    try:
        return WorkflowGraphDocument.model_validate(graph)
    except ValidationError as error:
        logger.exception("workflow_graph_read_failed error_code=STORED_GRAPH_INVALID")
        raise AppError(500, "STORED_WORKFLOW_GRAPH_INVALID") from error


def _workflow_summary(workflow: Workflow) -> WorkflowSummaryRead:
    return WorkflowSummaryRead(
        id=workflow.id,
        workspace_id=workflow.workspace_id,
        owner_type=workflow.owner_type,
        owner_id=workflow.owner_id,
        project_id=workflow.project_id,
        reproduction_task_id=workflow.reproduction_task_id,
        name=workflow.name,
        description=workflow.description,
        revision=workflow.revision,
        current_version=workflow.current_version,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


def _workflow_read(workflow: Workflow, *, can_edit: bool) -> WorkflowRead:
    return WorkflowRead(
        **_workflow_summary(workflow).model_dump(),
        graph=_graph_read(workflow.graph),
        can_edit=can_edit,
    )


def _version_summary(version: WorkflowVersion) -> WorkflowVersionSummaryRead:
    return WorkflowVersionSummaryRead(
        id=version.id,
        workflow_id=version.workflow_id,
        version=version.version,
        name=version.name,
        description=version.description,
        schema_version=version.schema_version,
        content_hash=version.content_hash,
        created_by=version.created_by,
        created_at=version.created_at,
    )


def _version_read(version: WorkflowVersion) -> WorkflowVersionRead:
    return WorkflowVersionRead(**_version_summary(version).model_dump(), graph=_graph_read(version.graph))


@router.get("/api/v1/workflow-components", response_model=list[WorkflowComponentRead])
def read_workflow_components(
    identity: DemoIdentity = Depends(get_demo_identity),
) -> list[WorkflowComponentRead]:
    components = list_workflow_components()
    logger.info(
        "workflow_component_catalog_read actor_id=%s component_count=%s executor_count=%s",
        identity.user_id,
        len(components),
        sum(1 for item in components if item["execution_available"]),
    )
    return [WorkflowComponentRead.model_validate(item) for item in components]


@router.get("/api/v1/projects/{project_id}/workflows", response_model=list[WorkflowSummaryRead])
def read_project_workflows(
    project_id: UUID,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> list[WorkflowSummaryRead]:
    return [_workflow_summary(item) for item in list_project_workflows(session, identity, project_id)]


@router.post(
    "/api/v1/projects/{project_id}/workflows",
    response_model=WorkflowRead,
    status_code=201,
)
def create_project_workflow_route(
    project_id: UUID,
    payload: WorkflowCreate,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> WorkflowRead:
    workflow = create_project_workflow(
        session,
        identity,
        project_id,
        name=payload.name,
        description=payload.description,
    )
    logger.info(
        "workflow_created project_id=%s workflow_id=%s actor_id=%s revision=%s",
        project_id,
        workflow.id,
        identity.user_id,
        workflow.revision,
    )
    return _workflow_read(workflow, can_edit=True)


@router.get(
    "/api/v1/reproductions/{task_id}/workflows",
    response_model=list[WorkflowSummaryRead],
)
def read_reproduction_workflows(
    task_id: UUID,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> list[WorkflowSummaryRead]:
    workflows = list_reproduction_workflows(session, identity, task_id)
    logger.info(
        "reproduction_workflows_read task_id=%s actor_id=%s workflow_count=%s",
        task_id,
        identity.user_id,
        len(workflows),
    )
    return [_workflow_summary(item) for item in workflows]


@router.post(
    "/api/v1/reproductions/{task_id}/workflows",
    response_model=WorkflowRead,
    status_code=201,
)
def create_reproduction_workflow_route(
    task_id: UUID,
    payload: WorkflowCreate,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> WorkflowRead:
    workflow = create_reproduction_workflow(
        session,
        identity,
        task_id,
        name=payload.name,
        description=payload.description,
    )
    logger.info(
        "reproduction_workflow_created task_id=%s workflow_id=%s actor_id=%s revision=%s",
        task_id,
        workflow.id,
        identity.user_id,
        workflow.revision,
    )
    return _workflow_read(workflow, can_edit=True)


@router.get("/api/v1/workflows/{workflow_id}", response_model=WorkflowRead)
def read_workflow(
    workflow_id: UUID,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> WorkflowRead:
    workflow, membership_role = get_visible_workflow(session, identity, workflow_id)
    can_edit = identity.role == "operator" and membership_role == "operator"
    return _workflow_read(workflow, can_edit=can_edit)


@router.patch("/api/v1/workflows/{workflow_id}", response_model=WorkflowRead)
def update_workflow(
    workflow_id: UUID,
    payload: WorkflowUpdate,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> WorkflowRead:
    graph = payload.graph.model_dump(mode="json", by_alias=True)
    try:
        workflow = update_workflow_draft(
            session,
            identity,
            workflow_id,
            expected_revision=payload.revision,
            name=payload.name,
            description=payload.description,
            graph=graph,
        )
    except AppError as error:
        if error.code == "WORKFLOW_REVISION_CONFLICT":
            logger.warning(
                "workflow_save_conflict workflow_id=%s actor_id=%s expected_revision=%s",
                workflow_id,
                identity.user_id,
                payload.revision,
            )
        raise
    logger.info(
        "workflow_saved workflow_id=%s actor_id=%s revision=%s node_count=%s edge_count=%s",
        workflow.id,
        identity.user_id,
        workflow.revision,
        len(graph["nodes"]),
        len(graph["edges"]),
    )
    return _workflow_read(workflow, can_edit=True)


@router.post("/api/v1/workflows/{workflow_id}/validations", response_model=WorkflowValidationRead)
def validate_workflow(
    workflow_id: UUID,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> WorkflowValidationRead:
    workflow, _role = get_visible_workflow(session, identity, workflow_id)
    structural_issues = validate_workflow_graph(workflow.graph)
    contract_issues = validate_workflow_component_contracts(workflow.graph)
    issues = [
        *({"scope": "structure", **item} for item in structural_issues),
        *({"scope": "component", **item} for item in contract_issues),
    ]
    logger.info(
        "workflow_validated workflow_id=%s actor_id=%s revision=%s structural_status=%s contract_status=%s issue_count=%s",
        workflow.id,
        identity.user_id,
        workflow.revision,
        "invalid" if structural_issues else "valid",
        "invalid" if contract_issues else "valid",
        len(issues),
    )
    return WorkflowValidationRead(
        workflow_id=workflow.id,
        revision=workflow.revision,
        structural_status="invalid" if structural_issues else "valid",
        contract_status="invalid" if contract_issues else "valid",
        execution_blockers=["COMPONENT_EXECUTORS_UNAVAILABLE", "EXECUTION_ENGINE_UNAVAILABLE"],
        issues=[_workflow_validation_issue_read(item) for item in issues],
    )


@router.post(
    "/api/v1/workflows/{workflow_id}/versions",
    response_model=WorkflowVersionCreatedRead,
    status_code=201,
)
def create_workflow_version_route(
    workflow_id: UUID,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> WorkflowVersionCreatedRead:
    try:
        workflow, version, created = create_workflow_version(session, identity, workflow_id)
    except AppError as error:
        if error.code == "WORKFLOW_VALIDATION_BLOCKED":
            logger.warning(
                "workflow_version_blocked workflow_id=%s actor_id=%s error_code=%s",
                workflow_id,
                identity.user_id,
                error.code,
            )
        raise
    logger.info(
        "workflow_version_%s workflow_id=%s version=%s actor_id=%s content_hash=%s",
        "created" if created else "reused",
        workflow.id,
        version.version,
        identity.user_id,
        version.content_hash,
    )
    return WorkflowVersionCreatedRead(
        created=created,
        workflow=_workflow_summary(workflow),
        version=_version_summary(version),
    )


@router.get(
    "/api/v1/workflows/{workflow_id}/versions",
    response_model=list[WorkflowVersionSummaryRead],
)
def read_workflow_versions(
    workflow_id: UUID,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> list[WorkflowVersionSummaryRead]:
    workflow, _role = get_visible_workflow(session, identity, workflow_id)
    return [_version_summary(item) for item in workflow.versions]


@router.get(
    "/api/v1/workflows/{workflow_id}/versions/{version_number}",
    response_model=WorkflowVersionRead,
)
def read_workflow_version(
    workflow_id: UUID,
    version_number: int,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> WorkflowVersionRead:
    workflow, _role = get_visible_workflow(session, identity, workflow_id)
    version = next((item for item in workflow.versions if item.version == version_number), None)
    if version is None:
        raise AppError(404, "WORKFLOW_VERSION_NOT_FOUND")
    return _version_read(version)


@router.post(
    "/api/v1/workflows/{workflow_id}/versions/{version_number}/restore",
    response_model=WorkflowRead,
)
def restore_workflow_version_route(
    workflow_id: UUID,
    version_number: int,
    payload: WorkflowVersionRestore,
    session: Session = Depends(get_database_session),
    identity: DemoIdentity = Depends(get_demo_identity),
) -> WorkflowRead:
    try:
        workflow = restore_workflow_version_draft(
            session,
            identity,
            workflow_id,
            version_number,
            expected_revision=payload.revision,
        )
    except AppError as error:
        if error.code == "WORKFLOW_REVISION_CONFLICT":
            logger.warning(
                "workflow_version_restore_conflict workflow_id=%s actor_id=%s version=%s expected_revision=%s",
                workflow_id,
                identity.user_id,
                version_number,
                payload.revision,
            )
        raise
    logger.info(
        "workflow_version_restored_to_draft workflow_id=%s actor_id=%s version=%s revision=%s",
        workflow.id,
        identity.user_id,
        version_number,
        workflow.revision,
    )
    return _workflow_read(workflow, can_edit=True)
