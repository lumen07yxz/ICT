"""Versioned workflow node contracts; definitions do not imply an executor exists."""

from copy import deepcopy
from typing import Any

from app.services.local_csv_executor import (
    CSV_ARTIFACT_SOURCE_EXECUTOR_BINDING,
    CSV_ARTIFACT_SOURCE_EXECUTOR_VERSION,
    CSV_COLUMN_SELECT_EXECUTOR_BINDING,
    CSV_COLUMN_SELECT_EXECUTOR_VERSION,
    CSV_DESCRIPTIVE_SUMMARY_EXECUTOR_BINDING,
    CSV_DESCRIPTIVE_SUMMARY_EXECUTOR_VERSION,
    CSV_PREFLIGHT_DEPENDENCY_REQUIREMENT,
    CSV_PREFLIGHT_EXECUTOR_VERSION,
    local_csv_implementation_digest,
)
from app.services.local_csv_folder_executor import (
    CSV_FOLDER_MAX_FILES,
    CSV_FOLDER_QUALITY_EXECUTOR_BINDING,
    CSV_FOLDER_QUALITY_EXECUTOR_VERSION,
    CSV_FOLDER_SOURCE_EXECUTOR_BINDING,
    CSV_FOLDER_SOURCE_EXECUTOR_VERSION,
    csv_folder_implementation_digest,
)
from app.services.network_crossref_executor import (
    CROSSREF_DEPENDENCY_REQUIREMENT,
    CROSSREF_EXECUTOR_BINDING,
    CROSSREF_EXECUTOR_VERSION,
    crossref_implementation_digest,
)


def _port(port_id: str, label: str, data_type: str) -> dict[str, Any]:
    return {
        "id": port_id,
        "label": label,
        "data_type": data_type,
        "required": True,
        "multiple": False,
    }


def _string_parameter(
    label: str,
    description: str,
    *,
    required: bool = True,
    default: str = "",
    max_length: int | None = None,
) -> dict[str, Any]:
    result = {
        "type": "string",
        "title": label,
        "description": description,
        "default": default,
        "minLength": 1 if required else 0,
    }
    if max_length is not None:
        result["maxLength"] = max_length
    return result


def _component(
    component_id: str,
    category: str,
    title: str,
    description: str,
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    properties: dict[str, dict[str, Any]],
    required_parameters: list[str],
    *,
    version: str = "1.0.0",
    execution_target: str = "local",
    dependencies: list[str] | None = None,
    permissions: list[str] | None = None,
    executor_binding: str | None = None,
    executor_version: str | None = None,
    implementation_digest: str | None = None,
    resource_limits: dict[str, int | None] | None = None,
    cache_policy: str = "not_configured",
) -> dict[str, Any]:
    return {
        "schema_version": "ict.component.v1",
        "component_id": component_id,
        "version": version,
        "category": category,
        "title": title,
        "description": description,
        "inputs": inputs,
        "outputs": outputs,
        "parameter_schema": {
            "type": "object",
            "properties": properties,
            "required": required_parameters,
            "additionalProperties": False,
        },
        "executor_binding": executor_binding,
        "executor_version": executor_version,
        "implementation_digest": implementation_digest,
        "execution_target": execution_target,
        "dependencies": list(dependencies or []),
        "permissions": list(permissions or ["project:resource:read"]),
        "resource_limits": resource_limits or {
            "timeout_seconds": None,
            "cpu_millicores": None,
            "memory_mb": None,
            "gpu_count": None,
            "gpu_memory_mb": None,
            "max_input_bytes": None,
        },
        "cache_policy": cache_policy,
        "error_types": [],
        # Availability is determined by the runtime that owns this component list.
        "execution_available": False,
    }


# These are versioned contracts aligned with ENG-5.1/5.2. Only components with
# an audited executor in the owning runtime are runnable; all others remain
# available for editing and validation without pretending to execute.
_COMPONENTS: tuple[dict[str, Any], ...] = (
    _component(
        "ict.paper.crossref_metadata",
        "文献与证据",
        "Crossref DOI 元数据",
        "运行时向固定 Crossref HTTPS 端点读取 DOI 的公开书目信息；不会上传本机文件或读取摘要。",
        [],
        [_port("paper_metadata", "文献元数据", "PaperMetadataRef")],
        {
            "doi": {
                "type": "string",
                "title": "DOI",
                "description": "填写 DOI 或 doi.org 链接。运行时只访问 api.crossref.org。",
                "default": "",
                "minLength": 1,
                "maxLength": 300,
            }
        },
        ["doi"],
        execution_target="network",
        dependencies=[CROSSREF_DEPENDENCY_REQUIREMENT],
        permissions=["network:crossref:metadata:read"],
        executor_binding=CROSSREF_EXECUTOR_BINDING,
        executor_version=CROSSREF_EXECUTOR_VERSION,
        implementation_digest=crossref_implementation_digest(),
        resource_limits={
            "timeout_seconds": 20,
            "cpu_millicores": 250,
            "memory_mb": 128,
            "gpu_count": 0,
            "gpu_memory_mb": 0,
            "max_input_bytes": 0,
        },
        cache_policy="not_configured",
    ),
    _component(
        "ict.data.dataset_reference",
        "数据输入",
        "数据集引用",
        "在项目中引用一个已有的数据集及其固定版本。",
        [],
        [_port("dataset", "数据集", "DatasetRef")],
        {
            "dataset_id": _string_parameter("数据集 ID", "填写项目内数据集 ID。"),
            "dataset_version": _string_parameter("数据版本", "填写不可变数据版本 ID。"),
        },
        ["dataset_id", "dataset_version"],
        execution_target="platform",
    ),
    _component(
        "ict.data.csv_folder_source",
        "数据输入",
        "本机 CSV 文件夹",
        f"从本机选定文件夹读取 1 至 {CSV_FOLDER_MAX_FILES} 个已授权 CSV 产物；目录内容不上传平台。",
        [],
        [_port("files", "CSV 文件集合", "CsvFileCollectionRef")],
        {
            "files_json": _string_parameter(
                "本机 CSV 文件夹",
                "选择目录后递归导入 CSV 文件；每个文件以 ArtifactHandle 进入工作流，文件夹总大小不超过 100 MiB。",
                max_length=200_000,
            )
        },
        ["files_json"],
        permissions=["local:artifact:read"],
        executor_binding=CSV_FOLDER_SOURCE_EXECUTOR_BINDING,
        executor_version=CSV_FOLDER_SOURCE_EXECUTOR_VERSION,
        implementation_digest=csv_folder_implementation_digest(),
        resource_limits={
            "timeout_seconds": 120,
            "cpu_millicores": 250,
            "memory_mb": 128,
            "gpu_count": 0,
            "gpu_memory_mb": 0,
            "max_input_bytes": 100 * 1024 * 1024,
        },
        cache_policy="input_signature",
    ),
    _component(
        "ict.data.quality_check",
        "数据检验",
        "CSV 文件夹质量检查",
        "离线逐文件检查 CSV 表头、行宽、必需字段、缺失率和唯一键；生成可追溯报告，不修改输入文件。",
        [_port("files", "CSV 文件集合", "CsvFileCollectionRef")],
        [_port("quality_report", "逐文件质量报告", "CsvFolderQualityReportRef")],
        {
            "required_columns": _string_parameter(
                "必需字段",
                "可选；按字段名填写并用英文逗号分隔。缺少必需字段的文件会标为阻断。",
                required=False,
                max_length=2_000,
            ),
            "unique_key_columns": _string_parameter(
                "唯一键字段",
                "可选；按字段名填写并用英文逗号分隔。重复键会标为阻断。",
                required=False,
                max_length=2_000,
            ),
            "max_missing_rate": _string_parameter(
                "缺失率阈值",
                "0 到 1 之间的小数；任一字段缺失率超过阈值时标为警告。",
                default="0.05",
                max_length=8,
            ),
        },
        ["max_missing_rate"],
        version="2.0.0",
        permissions=["local:artifact:read", "local:artifact:write"],
        executor_binding=CSV_FOLDER_QUALITY_EXECUTOR_BINDING,
        executor_version=CSV_FOLDER_QUALITY_EXECUTOR_VERSION,
        implementation_digest=csv_folder_implementation_digest(),
        resource_limits={
            "timeout_seconds": 600,
            "cpu_millicores": 500,
            "memory_mb": 512,
            "gpu_count": 0,
            "gpu_memory_mb": 0,
            "max_input_bytes": 100 * 1024 * 1024,
        },
        cache_policy="input_signature",
    ),
    _component(
        "ict.medical.image_preparation",
        "数据处理",
        "医学影像预处理",
        "将已验证的数据引用转换为模型可消费的影像批次。",
        [_port("dataset", "已验证数据", "ValidatedDatasetRef")],
        [_port("image_batch", "影像批次", "ImageBatchRef")],
        {"preprocessor_id": _string_parameter("预处理配置 ID", "填写已登记的预处理配置 ID。")},
        ["preprocessor_id"],
        execution_target="local",
    ),
    _component(
        "ict.medical.model_inference",
        "模型推理",
        "模型推理",
        "将影像批次送入指定模型配置，输出预测结果引用。",
        [_port("image_batch", "影像批次", "ImageBatchRef")],
        [_port("predictions", "预测结果", "PredictionSet")],
        {"model_id": _string_parameter("模型配置 ID", "填写已登记的模型配置 ID。")},
        ["model_id"],
        execution_target="platform",
    ),
    _component(
        "ict.data.csv_artifact_source",
        "数据输入",
        "本机 CSV 产物引用",
        "从本机已授权产物库读取 CSV ArtifactHandle 作为数据流输入；不访问任意文件路径，也不会上传文件。",
        [],
        [_port("csv", "本机 CSV", "CsvArtifactRef")],
        {
            "artifact_id": _string_parameter(
                "本机 CSV 产物 ID",
                "先在画布导入 CSV，再引用导入后显示的本机产物 ID。",
            )
        },
        ["artifact_id"],
        execution_target="local",
        permissions=["local:artifact:read"],
        executor_binding=CSV_ARTIFACT_SOURCE_EXECUTOR_BINDING,
        executor_version=CSV_ARTIFACT_SOURCE_EXECUTOR_VERSION,
        implementation_digest=local_csv_implementation_digest(),
        resource_limits={
            "timeout_seconds": 15,
            "cpu_millicores": 100,
            "memory_mb": 64,
            "gpu_count": 0,
            "gpu_memory_mb": 0,
            "max_input_bytes": 100 * 1024 * 1024,
        },
        cache_policy="input_signature",
    ),
    _component(
        "ict.data.csv_select_columns",
        "数据处理",
        "CSV 字段选择",
        "在本机按字段名选择并重排 CSV 列，输出可继续连接结构预检；不会覆盖输入文件或上传内容。",
        [_port("csv", "本机 CSV", "CsvArtifactRef")],
        [_port("selected_csv", "筛选后 CSV", "CsvArtifactRef")],
        {
            "columns": _string_parameter(
                "保留字段",
                "输入精确字段名并用英文逗号分隔；输出列按填写顺序排列。",
            )
        },
        ["columns"],
        execution_target="local",
        permissions=["local:artifact:read", "local:artifact:write"],
        executor_binding=CSV_COLUMN_SELECT_EXECUTOR_BINDING,
        executor_version=CSV_COLUMN_SELECT_EXECUTOR_VERSION,
        implementation_digest=local_csv_implementation_digest(),
        resource_limits={
            "timeout_seconds": 120,
            "cpu_millicores": 500,
            "memory_mb": 256,
            "gpu_count": 0,
            "gpu_memory_mb": 0,
            "max_input_bytes": 100 * 1024 * 1024,
        },
        cache_policy="input_signature",
    ),
    _component(
        "ict.data.csv_descriptive_summary",
        "数据检验",
        "CSV 描述统计摘要",
        "在本机流式汇总字段缺失率、数值列范围与均值、类别频数；仅作探索性摘要，不构成科研结果。",
        [_port("csv", "本机 CSV", "CsvArtifactRef")],
        [_port("summary_report", "描述统计报告", "CsvDescriptiveSummaryRef")],
        {},
        [],
        execution_target="local",
        permissions=["local:artifact:read", "local:artifact:write"],
        executor_binding=CSV_DESCRIPTIVE_SUMMARY_EXECUTOR_BINDING,
        executor_version=CSV_DESCRIPTIVE_SUMMARY_EXECUTOR_VERSION,
        implementation_digest=local_csv_implementation_digest(),
        resource_limits={
            "timeout_seconds": 120,
            "cpu_millicores": 500,
            "memory_mb": 512,
            "gpu_count": 0,
            "gpu_memory_mb": 0,
            "max_input_bytes": 100 * 1024 * 1024,
        },
        cache_policy="input_signature",
    ),
    _component(
        "ict.data.csv_manifest_preflight_input",
        "数据检验",
        "本机 CSV 结构预检（连接输入）",
        "接收上游本机 CSV ArtifactHandle，在本机检查通用字段、重复记录和分组拆分结构；报告不是科研结果。",
        [_port("csv", "本机 CSV", "CsvArtifactRef")],
        [_port("quality_report", "结构报告", "CsvQualityReportRef")],
        {},
        [],
        execution_target="local",
        dependencies=[CSV_PREFLIGHT_DEPENDENCY_REQUIREMENT],
        permissions=["local:artifact:read", "local:artifact:write"],
        executor_binding="ict.local.csv_manifest_preflight",
        executor_version=CSV_PREFLIGHT_EXECUTOR_VERSION,
        implementation_digest=local_csv_implementation_digest(),
        resource_limits={
            "timeout_seconds": 120,
            "cpu_millicores": 500,
            "memory_mb": 512,
            "gpu_count": 0,
            "gpu_memory_mb": 0,
            "max_input_bytes": 100 * 1024 * 1024,
        },
        cache_policy="input_signature",
    ),
    _component(
        "ict.data.csv_manifest_preflight",
        "数据检验",
        "本机 CSV 结构预检（快捷）",
        "在本机检查已导入 CSV 的通用字段和结构；该检查不是科研结果。",
        [],
        [_port("quality_report", "结构报告", "CsvQualityReportRef")],
        {
            "artifact_id": _string_parameter(
                "本机 CSV 产物 ID",
                "选择已经授权并导入本机的 CSV ArtifactHandle。文件不会上传到平台。",
            )
        },
        ["artifact_id"],
        execution_target="local",
        dependencies=[CSV_PREFLIGHT_DEPENDENCY_REQUIREMENT],
        permissions=["local:artifact:read", "local:artifact:write"],
        executor_binding="ict.local.csv_manifest_preflight",
        executor_version=CSV_PREFLIGHT_EXECUTOR_VERSION,
        implementation_digest=local_csv_implementation_digest(),
        resource_limits={
            "timeout_seconds": 120,
            "cpu_millicores": 500,
            "memory_mb": 512,
            "gpu_count": 0,
            "gpu_memory_mb": 0,
            "max_input_bytes": 100 * 1024 * 1024,
        },
        cache_policy="input_signature",
    ),
)

_BY_ID = {item["component_id"]: item for item in _COMPONENTS}


def list_workflow_components(
    *,
    available_execution_targets: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return detached contracts with availability evaluated by the owning runtime."""
    available = available_execution_targets or set()
    components = deepcopy(list(_COMPONENTS))
    for component in components:
        component["execution_available"] = (
            component["executor_binding"] is not None
            and component["execution_target"] in available
        )
    return components


def get_workflow_component(
    component_id: str,
    *,
    available_execution_targets: set[str] | None = None,
) -> dict[str, Any] | None:
    """Return one detached versioned contract, if it is registered."""
    component = _BY_ID.get(component_id)
    if component is None:
        return None
    resolved = deepcopy(component)
    available = available_execution_targets or set()
    resolved["execution_available"] = (
        resolved["executor_binding"] is not None
        and resolved["execution_target"] in available
    )
    return resolved
