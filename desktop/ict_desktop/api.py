"""Small, fail-closed client for the desktop workbench API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
import re
from uuid import UUID
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


OVERVIEW_PATH = "/api/v1/demo/projects/demo-research/overview"
HEALTH_PATH = "/health"
PROJECTS_PATH = "/api/v1/projects"
RUN_PROPOSALS_PATH = "/api/v1/run-proposals"
RUNS_PATH = "/api/v1/runs"
DEMO_QUALITY_REPORT_PATH = "/api/v1/projects/demo/demo-research/datasets/dataset-synthetic-v1/quality-report"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
PROPOSAL_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class DesktopApiError(RuntimeError):
    """Safe, user-facing API error that never contains response internals."""


@dataclass(frozen=True)
class DemoProjectOverview:
    project_id: str
    purpose: str
    data_status: str
    research_ready: bool
    dataset_versions: tuple[str, ...]
    pipeline_templates: tuple[str, ...]
    recent_public_runs: tuple[str, ...]


@dataclass(frozen=True)
class ProjectListItem:
    project_id: str
    name: str
    domain: str
    role: str


@dataclass(frozen=True)
class ProjectDatasetVersion:
    version: str
    source: str
    license_status: str
    research_ready: bool


@dataclass(frozen=True)
class ProjectDetail:
    project_id: str
    name: str
    domain: str
    role: str
    datasets: tuple[ProjectDatasetVersion, ...]


@dataclass(frozen=True)
class RunProposal:
    proposal_id: str
    project_id: str
    dataset_version: str
    pipeline_template: str
    parameters: dict[str, int]
    config_sha256: str
    trace_id: str
    status: str
    approved_by: str | None
    approved_at: str | None
    run_id: str | None
    created_at: str
    expires_at: str


@dataclass(frozen=True)
class Run:
    run_id: str
    proposal_id: str
    project_id: str
    dataset_version: str
    pipeline_template: str
    parameters: dict[str, int]
    config_sha256: str
    trace_id: str
    status: str
    result: dict[str, object] | None
    error_code: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    quality_status: str | None = None
    quality_rule_set_version: str | None = None
    quality_report_sha256: str | None = None


@dataclass(frozen=True)
class RunEvent:
    sequence: int
    status: str
    error_code: str | None
    occurred_at: str


@dataclass(frozen=True)
class PipelineFieldContract:
    field_type: str
    required: bool
    minimum: int | None
    maximum: int | None
    const: str | int | bool | None


@dataclass(frozen=True)
class TemplateResourceLimits:
    max_concurrent_runs: int
    soft_timeout_seconds: int
    hard_timeout_seconds: int


@dataclass(frozen=True)
class PipelineTemplateContract:
    template_id: str
    version: str
    manifest_sha256: str
    executor: str
    dataset_version: str
    permission_scope: str
    resource_limits: TemplateResourceLimits
    inputs: dict[str, PipelineFieldContract]
    parameters: dict[str, PipelineFieldContract]
    outputs: dict[str, PipelineFieldContract]
    states: tuple[str, ...]
    error_codes: tuple[str, ...]


@dataclass(frozen=True)
class DatasetQualityIssue:
    code: str
    severity: str
    message: str
    count: int
    line_numbers: tuple[int, ...]
    guidance: str


@dataclass(frozen=True)
class DatasetQualityReport:
    dataset_version: str
    status: str
    rule_set_version: str
    manifest_sha256: str
    row_count: int
    split_counts: tuple[tuple[str, int], ...]
    label_category_count: int
    issues: tuple[DatasetQualityIssue, ...]
    synthetic_only: bool
    research_ready: bool
    checked_at: str


def _is_string_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _parse_overview(value: object) -> DemoProjectOverview:
    if not isinstance(value, dict):
        raise DesktopApiError("后端返回的数据不符合当前演示范围。")

    # Keep the desktop client on the same synthetic-only allowlist as the API.
    if (
        value.get("project_id") != "demo-research"
        or not isinstance(value.get("purpose"), str)
        or value.get("data_status") != "synthetic_only"
        or value.get("research_ready") is not False
        or not _is_string_list(value.get("dataset_versions"))
        or not _is_string_list(value.get("pipeline_templates"))
        or not _is_string_list(value.get("recent_public_runs"))
    ):
        raise DesktopApiError("后端返回的数据不符合当前演示范围。")

    return DemoProjectOverview(
        project_id="demo-research",
        purpose=value["purpose"],
        data_status="synthetic_only",
        research_ready=False,
        dataset_versions=tuple(value["dataset_versions"]),
        pipeline_templates=tuple(value["pipeline_templates"]),
        recent_public_runs=tuple(value["recent_public_runs"]),
    )


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _parse_project_list(value: object) -> list[ProjectListItem]:
    if not isinstance(value, list):
        raise DesktopApiError("团队项目服务返回的数据格式不正确。")

    projects: list[ProjectListItem] = []
    for item in value:
        if not isinstance(item, dict):
            raise DesktopApiError("团队项目服务返回的数据格式不正确。")
        try:
            project_id = str(UUID(item.get("id", "")))
        except (ValueError, TypeError, AttributeError) as exc:
            raise DesktopApiError("团队项目服务返回的数据格式不正确。") from exc
        name = item.get("name")
        domain = item.get("domain")
        role = item.get("role")
        if (
            not _non_empty_string(name)
            or not _non_empty_string(domain)
            or role not in {"operator", "viewer"}
        ):
            raise DesktopApiError("团队项目服务返回的数据格式不正确。")
        projects.append(ProjectListItem(project_id, name, domain, role))
    return projects


def _parse_project_detail(value: object) -> ProjectDetail:
    if not isinstance(value, dict):
        raise DesktopApiError("团队项目服务返回的数据格式不正确。")
    try:
        project_id = str(UUID(value.get("id", "")))
    except (ValueError, TypeError, AttributeError) as exc:
        raise DesktopApiError("团队项目服务返回的数据格式不正确。") from exc

    name = value.get("name")
    domain = value.get("domain")
    role = value.get("role")
    datasets_value = value.get("datasets")
    if (
        not _non_empty_string(name)
        or not _non_empty_string(domain)
        or role not in {"operator", "viewer"}
        or not isinstance(datasets_value, list)
    ):
        raise DesktopApiError("团队项目服务返回的数据格式不正确。")

    datasets: list[ProjectDatasetVersion] = []
    for dataset in datasets_value:
        if not isinstance(dataset, dict):
            raise DesktopApiError("团队项目服务返回的数据格式不正确。")
        version = dataset.get("version")
        source = dataset.get("source")
        license_status = dataset.get("license_status")
        research_ready = dataset.get("research_ready")
        if (
            not _non_empty_string(version)
            or not _non_empty_string(source)
            or not _non_empty_string(license_status)
            or not isinstance(research_ready, bool)
        ):
            raise DesktopApiError("团队项目服务返回的数据格式不正确。")
        # Deliberately expose only dataset summary fields, never storage references.
        datasets.append(ProjectDatasetVersion(version, source, license_status, research_ready))

    return ProjectDetail(project_id, name, domain, role, tuple(datasets))


def _parse_run_proposals(value: object) -> list[RunProposal]:
    """Accept only the small proposal DTO; reject storage refs or unexpected fields."""
    if not isinstance(value, list):
        raise DesktopApiError("团队提案服务返回的数据格式不正确。")

    expected_fields = {
        "id",
        "project_id",
        "dataset_version",
        "pipeline_template",
        "parameters",
        "config_sha256",
        "trace_id",
        "status",
        "approved_by",
        "approved_at",
        "run_id",
        "created_at",
        "expires_at",
    }
    proposals: list[RunProposal] = []
    for item in value:
        if not isinstance(item, dict) or set(item) != expected_fields:
            raise DesktopApiError("团队提案服务返回的数据格式不正确。")
        try:
            proposal_id = str(UUID(item["id"]))
            project_id = str(UUID(item["project_id"]))
        except (ValueError, TypeError, AttributeError) as exc:
            raise DesktopApiError("团队提案服务返回的数据格式不正确。") from exc

        dataset_version = item.get("dataset_version")
        pipeline_template = item.get("pipeline_template")
        parameters = item.get("parameters")
        config_sha256 = item.get("config_sha256")
        trace_id = item.get("trace_id")
        status_value = item.get("status")
        approved_by = item.get("approved_by")
        approved_at = item.get("approved_at")
        run_id_value = item.get("run_id")
        created_at = item.get("created_at")
        expires_at = item.get("expires_at")
        if (
            dataset_version != "dataset-synthetic-v1"
            or pipeline_template != "research-smoke-v1"
            or not isinstance(parameters, dict)
            or set(parameters) != {"sample_limit"}
            or type(parameters.get("sample_limit")) is not int
            or not 1 <= parameters["sample_limit"] <= 100
            or not isinstance(config_sha256, str)
            or not PROPOSAL_HASH_PATTERN.fullmatch(config_sha256)
            or status_value not in ("pending_approval", "expired", "approved")
            or not isinstance(trace_id, str)
            or not isinstance(created_at, str)
            or not isinstance(expires_at, str)
        ):
            raise DesktopApiError("团队提案服务返回的数据格式不正确。")
        try:
            trace_id = str(UUID(trace_id))
            run_id = str(UUID(run_id_value)) if run_id_value is not None else None
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            approved = datetime.fromisoformat(approved_at.replace("Z", "+00:00")) if approved_at else None
        except (ValueError, TypeError, AttributeError) as exc:
            raise DesktopApiError("团队提案服务返回的数据格式不正确。") from exc
        if (
            expires <= created
            or (status_value == "approved" and (not _non_empty_string(approved_by) or approved is None or run_id is None))
            or (status_value != "approved" and (approved_by is not None or approved_at is not None or run_id is not None))
        ):
            raise DesktopApiError("团队提案服务返回的数据格式不正确。")

        proposals.append(
            RunProposal(
                proposal_id=proposal_id,
                project_id=project_id,
                dataset_version=dataset_version,
                pipeline_template=pipeline_template,
                parameters={"sample_limit": parameters["sample_limit"]},
                config_sha256=config_sha256,
                trace_id=trace_id,
                status=status_value,
                approved_by=approved_by,
                approved_at=approved_at,
                run_id=run_id,
                created_at=created_at,
                expires_at=expires_at,
            )
        )
    return proposals


def _parse_run(value: object) -> Run:
    """Accept only the fixed, small run DTO and its synthetic result shape."""
    expected_fields = {
        "id", "proposal_id", "project_id", "dataset_version", "pipeline_template",
        "parameters", "config_sha256", "trace_id", "status", "result", "error_code",
        "created_at", "started_at", "finished_at", "quality_status",
        "quality_rule_set_version", "quality_report_sha256",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise DesktopApiError("运行记录服务返回的数据格式不正确。")
    try:
        run_id = str(UUID(value["id"]))
        proposal_id = str(UUID(value["proposal_id"]))
        project_id = str(UUID(value["project_id"]))
        trace_id = str(UUID(value["trace_id"]))
    except (ValueError, TypeError, AttributeError) as exc:
        raise DesktopApiError("运行记录服务返回的数据格式不正确。") from exc

    parameters = value.get("parameters")
    status_value = value.get("status")
    result_value = value.get("result")
    error_code = value.get("error_code")
    created_at = value.get("created_at")
    started_at = value.get("started_at")
    finished_at = value.get("finished_at")
    quality_status = value.get("quality_status")
    quality_rule_set_version = value.get("quality_rule_set_version")
    quality_report_sha256 = value.get("quality_report_sha256")
    quality_snapshot_empty = (
        quality_status is None
        and quality_rule_set_version is None
        and quality_report_sha256 is None
    )
    quality_snapshot_valid = (
        quality_status in ("success", "warning")
        and quality_rule_set_version == "generic-manifest-v1"
        and isinstance(quality_report_sha256, str)
        and PROPOSAL_HASH_PATTERN.fullmatch(quality_report_sha256)
    )
    if (
        value.get("dataset_version") != "dataset-synthetic-v1"
        or value.get("pipeline_template") != "research-smoke-v1"
        or not isinstance(parameters, dict)
        or set(parameters) != {"sample_limit"}
        or type(parameters.get("sample_limit")) is not int
        or not 1 <= parameters["sample_limit"] <= 100
        or not isinstance(value.get("config_sha256"), str)
        or not PROPOSAL_HASH_PATTERN.fullmatch(value["config_sha256"])
        or status_value not in ("queued", "running", "succeeded", "failed")
        or (error_code is not None and not _non_empty_string(error_code))
        or (status_value == "failed" and error_code is None)
        or (status_value != "failed" and error_code is not None)
        or not isinstance(created_at, str)
        or (started_at is not None and not isinstance(started_at, str))
        or (finished_at is not None and not isinstance(finished_at, str))
        or not (quality_snapshot_empty or quality_snapshot_valid)
    ):
        raise DesktopApiError("运行记录服务返回的数据格式不正确。")

    if status_value == "succeeded":
        expected_result_fields = {"task", "processed_count", "synthetic_only", "research_ready", "message"}
        if (
            not isinstance(result_value, dict)
            or set(result_value) != expected_result_fields
            or result_value.get("task") != "synthetic_smoke"
            or type(result_value.get("processed_count")) is not int
            or result_value["processed_count"] != parameters["sample_limit"]
            or result_value.get("synthetic_only") is not True
            or result_value.get("research_ready") is not False
            or result_value.get("message") != "集成冒烟任务完成。"
        ):
            raise DesktopApiError("运行记录服务返回的数据格式不正确。")
    elif result_value is not None:
        raise DesktopApiError("运行记录服务返回的数据格式不正确。")

    for timestamp in (created_at, started_at, finished_at):
        if timestamp is not None:
            try:
                datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError as exc:
                raise DesktopApiError("运行记录服务返回的数据格式不正确。") from exc

    return Run(
        run_id=run_id,
        proposal_id=proposal_id,
        project_id=project_id,
        dataset_version="dataset-synthetic-v1",
        pipeline_template="research-smoke-v1",
        parameters={"sample_limit": parameters["sample_limit"]},
        config_sha256=value["config_sha256"],
        trace_id=trace_id,
        status=status_value,
        result=result_value,
        error_code=error_code,
        created_at=created_at,
        started_at=started_at,
        finished_at=finished_at,
        quality_status=quality_status,
        quality_rule_set_version=quality_rule_set_version,
        quality_report_sha256=quality_report_sha256,
    )


def _parse_run_events(value: object) -> list[RunEvent]:
    """Accept only the fixed, ordered event fields returned by the run API."""
    if not isinstance(value, list) or len(value) > 3:
        raise DesktopApiError("运行事件服务返回的数据格式不正确。")

    events: list[RunEvent] = []
    expected_fields = {"sequence", "status", "error_code", "occurred_at"}
    allowed_error_codes = {"QUEUE_UNAVAILABLE", "WORKER_EXECUTION_FAILED"}
    expected_statuses = {1: "queued", 2: "running"}
    previous_sequence = 0
    for item in value:
        if not isinstance(item, dict) or set(item) != expected_fields:
            raise DesktopApiError("运行事件服务返回的数据格式不正确。")
        sequence = item.get("sequence")
        status = item.get("status")
        error_code = item.get("error_code")
        occurred_at = item.get("occurred_at")
        expected_status = expected_statuses.get(sequence) if type(sequence) is int else None
        if sequence == 3 and status in ("succeeded", "failed"):
            expected_status = status
        if (
            type(sequence) is not int
            or sequence not in (1, 2, 3)
            or sequence <= previous_sequence
            or status != expected_status
            or (
                error_code is not None
                and (not isinstance(error_code, str) or error_code not in allowed_error_codes)
            )
            or (status != "failed" and error_code is not None)
            or not isinstance(occurred_at, str)
        ):
            raise DesktopApiError("运行事件服务返回的数据格式不正确。")
        try:
            parsed_at = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise DesktopApiError("运行事件服务返回的数据格式不正确。") from exc
        if parsed_at.tzinfo is None or parsed_at.utcoffset() is None:
            raise DesktopApiError("运行事件服务返回的数据格式不正确。")
        events.append(
            RunEvent(
                sequence=sequence,
                status=status,
                error_code=error_code,
                occurred_at=occurred_at,
            )
        )
        previous_sequence = sequence
    return events


def _parse_template_field_map(
    value: object,
    expected: dict[str, dict[str, object]],
) -> dict[str, PipelineFieldContract]:
    """Accept only fields implemented by the one compiled synthetic executor."""
    if not isinstance(value, dict) or set(value) != set(expected):
        raise DesktopApiError("模板说明服务返回的数据格式不正确。")

    fields: dict[str, PipelineFieldContract] = {}
    for name, expected_field in expected.items():
        item = value.get(name)
        if not isinstance(item, dict) or set(item) != {
            "type", "required", "minimum", "maximum", "const"
        }:
            raise DesktopApiError("模板说明服务返回的数据格式不正确。")
        if any(type(item[key]) is not type(expected_value) for key, expected_value in expected_field.items()):
            # Optional values are always null in the JSON contract.
            if not all(
                item[key] is None if expected_value is None else type(item[key]) is type(expected_value)
                for key, expected_value in expected_field.items()
            ):
                raise DesktopApiError("模板说明服务返回的数据格式不正确。")
        if item != expected_field:
            raise DesktopApiError("模板说明服务返回的数据格式不正确。")
        fields[name] = PipelineFieldContract(
            field_type=item["type"],
            required=item["required"],
            minimum=item["minimum"],
            maximum=item["maximum"],
            const=item["const"],
        )
    return fields


def _parse_pipeline_template(value: object) -> PipelineTemplateContract:
    """Parse the exact safe DTO for the supported fixed template."""
    expected_fields = {
        "template_id",
        "version",
        "manifest_sha256",
        "executor",
        "dataset_version",
        "permission_scope",
        "resource_limits",
        "inputs",
        "parameters",
        "outputs",
        "states",
        "error_codes",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise DesktopApiError("模板说明服务返回的数据格式不正确。")

    version = value.get("version")
    resource_limits = value.get("resource_limits")
    states = value.get("states")
    error_codes = value.get("error_codes")
    if (
        value.get("template_id") != "research-smoke-v1"
        or not isinstance(version, str)
        or not re.fullmatch(r"\d+\.\d+\.\d+", version)
        or not isinstance(value.get("manifest_sha256"), str)
        or not PROPOSAL_HASH_PATTERN.fullmatch(value["manifest_sha256"])
        or value.get("executor") != "synthetic_smoke_v1"
        or value.get("dataset_version") != "dataset-synthetic-v1"
        or value.get("permission_scope") != "synthetic_dataset_manifest_read_only"
        or not isinstance(resource_limits, dict)
        or set(resource_limits) != {
            "max_concurrent_runs", "soft_timeout_seconds", "hard_timeout_seconds"
        }
        or type(resource_limits.get("max_concurrent_runs")) is not int
        or resource_limits["max_concurrent_runs"] != 1
        or type(resource_limits.get("soft_timeout_seconds")) is not int
        or not 1 <= resource_limits["soft_timeout_seconds"] <= 25
        or type(resource_limits.get("hard_timeout_seconds")) is not int
        or not 2 <= resource_limits["hard_timeout_seconds"] <= 30
        or resource_limits["soft_timeout_seconds"] >= resource_limits["hard_timeout_seconds"]
        or states != ["queued", "running", "succeeded", "failed"]
        or error_codes != [
            "DATA_QUALITY_BLOCKED",
            "PROPOSAL_CONFIG_MISMATCH",
            "QUEUE_UNAVAILABLE",
            "WORKER_EXECUTION_FAILED",
        ]
    ):
        raise DesktopApiError("模板说明服务返回的数据格式不正确。")

    inputs = _parse_template_field_map(
        value["inputs"],
        {
            "dataset_version": {
                "type": "string",
                "required": True,
                "minimum": None,
                "maximum": None,
                "const": "dataset-synthetic-v1",
            }
        },
    )
    parameters = _parse_template_field_map(
        value["parameters"],
        {
            "sample_limit": {
                "type": "integer",
                "required": True,
                "minimum": 1,
                "maximum": 100,
                "const": None,
            }
        },
    )
    outputs = _parse_template_field_map(
        value["outputs"],
        {
            "task": {
                "type": "string", "required": True, "minimum": None,
                "maximum": None, "const": "synthetic_smoke",
            },
            "processed_count": {
                "type": "integer", "required": True, "minimum": 0,
                "maximum": None, "const": None,
            },
            "synthetic_only": {
                "type": "boolean", "required": True, "minimum": None,
                "maximum": None, "const": True,
            },
            "research_ready": {
                "type": "boolean", "required": True, "minimum": None,
                "maximum": None, "const": False,
            },
            "message": {
                "type": "string", "required": True, "minimum": None,
                "maximum": None, "const": None,
            },
        },
    )
    return PipelineTemplateContract(
        template_id="research-smoke-v1",
        version=version,
        manifest_sha256=value["manifest_sha256"],
        executor="synthetic_smoke_v1",
        dataset_version="dataset-synthetic-v1",
        permission_scope="synthetic_dataset_manifest_read_only",
        resource_limits=TemplateResourceLimits(**resource_limits),
        inputs=inputs,
        parameters=parameters,
        outputs=outputs,
        states=tuple(states),
        error_codes=tuple(error_codes),
    )


def _parse_quality_report(value: object) -> DatasetQualityReport:
    """Accept only the aggregate-only fixed synthetic server report contract."""
    expected_fields = {
        "dataset_version",
        "status",
        "rule_set_version",
        "manifest_sha256",
        "row_count",
        "split_counts",
        "label_category_count",
        "issues",
        "synthetic_only",
        "research_ready",
        "checked_at",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise DesktopApiError("服务器质量报告格式不正确。")

    status_value = value.get("status")
    split_counts = value.get("split_counts")
    issue_values = value.get("issues")
    manifest_sha256 = value.get("manifest_sha256")
    checked_at = value.get("checked_at")
    if (
        value.get("dataset_version") != "dataset-synthetic-v1"
        or status_value not in ("blocker", "warning", "success")
        or value.get("rule_set_version") != "generic-manifest-v1"
        or not isinstance(manifest_sha256, str)
        or not PROPOSAL_HASH_PATTERN.fullmatch(manifest_sha256)
        or type(value.get("row_count")) is not int
        or value["row_count"] < 0
        or type(value.get("label_category_count")) is not int
        or value["label_category_count"] < 0
        or not isinstance(split_counts, dict)
        or any(not isinstance(key, str) or type(count) is not int or count < 0 for key, count in split_counts.items())
        or not isinstance(issue_values, list)
        or value.get("synthetic_only") is not True
        or value.get("research_ready") is not False
        or not _non_empty_string(checked_at)
    ):
        raise DesktopApiError("服务器质量报告格式不正确。")

    issues: list[DatasetQualityIssue] = []
    for item in issue_values:
        if not isinstance(item, dict) or set(item) != {
            "code", "severity", "message", "count", "line_numbers", "guidance"
        }:
            raise DesktopApiError("服务器质量报告格式不正确。")
        lines = item.get("line_numbers")
        if (
            not _non_empty_string(item.get("code"))
            or not item["code"].isascii()
            or item.get("severity") not in ("blocker", "warning")
            or not _non_empty_string(item.get("message"))
            or type(item.get("count")) is not int
            or item["count"] < 0
            or not isinstance(lines, list)
            or any(type(line) is not int or line < 1 for line in lines)
            or not _non_empty_string(item.get("guidance"))
        ):
            raise DesktopApiError("服务器质量报告格式不正确。")
        issues.append(
            DatasetQualityIssue(
                code=item["code"],
                severity=item["severity"],
                message=item["message"],
                count=item["count"],
                line_numbers=tuple(lines),
                guidance=item["guidance"],
            )
        )

    derived_status = (
        "blocker"
        if any(issue.severity == "blocker" for issue in issues)
        else "warning"
        if any(issue.severity == "warning" for issue in issues)
        else "success"
    )
    if status_value != derived_status:
        raise DesktopApiError("服务器质量报告格式不正确。")
    try:
        datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DesktopApiError("服务器质量报告格式不正确。") from exc

    return DatasetQualityReport(
        dataset_version="dataset-synthetic-v1",
        status=status_value,
        rule_set_version="generic-manifest-v1",
        manifest_sha256=manifest_sha256,
        row_count=value["row_count"],
        split_counts=tuple(sorted(split_counts.items())),
        label_category_count=value["label_category_count"],
        issues=tuple(issues),
        synthetic_only=True,
        research_ready=False,
        checked_at=checked_at,
    )


class DemoProjectApiClient:
    """Read synthetic and membership-scoped project data from a local or HTTPS API."""

    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        parsed = urlsplit(base_url)
        host = (parsed.hostname or "").lower()
        is_loopback_http = parsed.scheme == "http" and host in LOOPBACK_HOSTS
        is_https = parsed.scheme == "https"
        if (
            not parsed.netloc
            or not host
            or not (is_loopback_http or is_https)
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise DesktopApiError("服务地址无效；远程服务必须使用 HTTPS。")

        self._base_url = base_url.rstrip("/") + "/"
        self._timeout_seconds = timeout_seconds

    def get_overview(self) -> DemoProjectOverview:
        payload = self._get_json(OVERVIEW_PATH)
        return _parse_overview(payload)

    def check_health(self) -> None:
        """Confirm the service is live without implying research readiness."""
        payload = self._get_json(HEALTH_PATH)
        if not isinstance(payload, dict) or payload.get("status") != "ok":
            raise DesktopApiError("服务当前不可用，请稍后重试。")

    def list_projects(self, access_token: str) -> list[ProjectListItem]:
        """List only projects granted to the caller; the token is request-scoped."""
        token = self._validate_access_token(access_token)
        return _parse_project_list(self._get_json(PROJECTS_PATH, access_token=token))

    def get_project(self, project_id: str, access_token: str) -> ProjectDetail:
        """Read one member-visible project by a validated UUID."""
        token = self._validate_access_token(access_token)
        try:
            safe_project_id = str(UUID(project_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise DesktopApiError("项目标识无效，无法读取详情。") from exc
        path = f"{PROJECTS_PATH}/{safe_project_id}"
        detail = _parse_project_detail(self._get_json(path, access_token=token))
        if detail.project_id != safe_project_id:
            raise DesktopApiError("团队项目服务返回的数据格式不正确。")
        return detail

    def get_project_template(
        self,
        project_id: str,
        template_id: str,
        access_token: str,
    ) -> PipelineTemplateContract:
        """Read one allowlisted template contract within the member project scope."""
        token = self._validate_access_token(access_token)
        try:
            safe_project_id = str(UUID(project_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise DesktopApiError("项目标识无效，无法读取模板说明。") from exc
        if template_id != "research-smoke-v1":
            raise DesktopApiError("当前模板不在允许查看的固定清单中。")
        path = f"{PROJECTS_PATH}/{safe_project_id}/templates/{template_id}"
        contract = _parse_pipeline_template(self._get_json(path, access_token=token))
        if contract.template_id != template_id:
            raise DesktopApiError("模板说明服务返回的数据格式不正确。")
        return contract

    def get_demo_quality_report(self, access_token: str) -> DatasetQualityReport:
        """Read a version-bound report using the current in-memory team token."""
        token = self._validate_access_token(access_token)
        return _parse_quality_report(
            self._get_json(DEMO_QUALITY_REPORT_PATH, access_token=token)
        )

    def list_run_proposals(self, access_token: str) -> list[RunProposal]:
        """Read proposals visible to the current member."""
        token = self._validate_access_token(access_token)
        return _parse_run_proposals(
            self._get_json(RUN_PROPOSALS_PATH, access_token=token)
        )

    def approve_run_proposal(self, proposal_id: str, access_token: str) -> Run:
        """Request approval through the authenticated operator-only API route."""
        token = self._validate_access_token(access_token)
        try:
            safe_proposal_id = str(UUID(proposal_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise DesktopApiError("提案标识无效，无法批准。") from exc
        path = f"{RUN_PROPOSALS_PATH}/{safe_proposal_id}/approve"
        return _parse_run(self._request_json(path, "POST", token))

    def list_runs(self, access_token: str) -> list[Run]:
        """Read only run records visible in the caller's member projects."""
        token = self._validate_access_token(access_token)
        payload = self._get_json(RUNS_PATH, access_token=token)
        if not isinstance(payload, list):
            raise DesktopApiError("运行记录服务返回的数据格式不正确。")
        return [_parse_run(item) for item in payload]

    def list_run_events(self, access_token: str, run_id: str) -> list[RunEvent]:
        """Read the fixed event timeline for one member-visible run."""
        token = self._validate_access_token(access_token)
        try:
            safe_run_id = str(UUID(run_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise DesktopApiError("运行标识无效，无法读取事件。") from exc
        payload = self._get_json(f"{RUNS_PATH}/{safe_run_id}/events", access_token=token)
        return _parse_run_events(payload)

    @staticmethod
    def _validate_access_token(access_token: str) -> str:
        if not isinstance(access_token, str) or not access_token.strip():
            raise DesktopApiError("请输入团队访问令牌。")
        return access_token.strip()

    def _get_json(self, path: str, access_token: str | None = None) -> object:
        return self._request_json(path, "GET", access_token)

    def _request_json(
        self,
        path: str,
        method: str,
        access_token: str | None = None,
    ) -> object:
        url = urljoin(self._base_url, path.lstrip("/"))
        headers = {"Accept": "application/json"}
        if access_token is not None:
            headers["Authorization"] = f"Bearer {access_token}"
        request = Request(url, headers=headers, data=b"" if method == "POST" else None, method=method)

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read())
        except HTTPError as exc:
            if access_token is not None:
                safe_messages = {
                    401: "访问令牌无效或已过期，请重新输入。",
                    403: "当前账号无权执行此操作。",
                    404: "项目或运行记录不存在，或当前账号无权查看。",
                    409: "数据质量检查阻断或请求状态已变化，请刷新后重试。",
                    503: "团队服务尚未配置完成，请联系管理员。",
                }
                safe_message = safe_messages.get(
                    exc.code, "暂时无法完成团队请求，请稍后重试。"
                )
            else:
                safe_message = "暂时无法读取项目概览，请稍后重试。"
            # HTTPError owns the response body; release it before raising a safe client error.
            exc.close()
            raise DesktopApiError(safe_message) from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise DesktopApiError("无法连接项目服务，请检查服务地址和网络后重试。") from exc

        return payload
