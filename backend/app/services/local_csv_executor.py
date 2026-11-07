"""Built-in local CSV executors for deterministic offline workflow steps."""

from __future__ import annotations

import asyncio
import csv
from collections import Counter
import hashlib
import importlib
import json
import logging
import math
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.services.local_artifacts import ArtifactHandle, LocalArtifactError, LocalArtifactStore
from app.services.local_csv_folder_executor import (
    LOCAL_FOLDER_EXECUTOR_PERMISSION_CAPABILITIES,
    build_local_csv_folder_executor_registry,
)
from app.services.workflow_scheduler import WorkflowNodeFailure


logger = logging.getLogger("ict.local_runtime.csv_preflight")
CSV_ARTIFACT_SOURCE_EXECUTOR_VERSION = "1.0.0"
CSV_ARTIFACT_SOURCE_EXECUTOR_BINDING = "ict.local.csv_artifact_source"
CSV_COLUMN_SELECT_EXECUTOR_VERSION = "1.0.0"
CSV_COLUMN_SELECT_EXECUTOR_BINDING = "ict.local.csv_select_columns"
CSV_DESCRIPTIVE_SUMMARY_EXECUTOR_VERSION = "1.0.0"
CSV_DESCRIPTIVE_SUMMARY_EXECUTOR_BINDING = "ict.local.csv_descriptive_summary"
CSV_PREFLIGHT_EXECUTOR_VERSION = "1.0.0"
CSV_SUMMARY_MAX_COLUMNS = 2_000
CSV_SUMMARY_CATEGORY_LIMIT = 500
CSV_SUMMARY_TOTAL_CATEGORY_LIMIT = 5_000
CSV_SUMMARY_CATEGORY_VALUE_LIMIT = 256
CSV_PREFLIGHT_DEPENDENCY_ID = "ict-desktop-manifest-quality"
CSV_PREFLIGHT_DEPENDENCY_VERSION = "1.0.0"
CSV_PREFLIGHT_DEPENDENCY_REQUIREMENT = (
    f"{CSV_PREFLIGHT_DEPENDENCY_ID}@{CSV_PREFLIGHT_DEPENDENCY_VERSION}"
)
LOCAL_EXECUTOR_PERMISSION_CAPABILITIES = {
    CSV_ARTIFACT_SOURCE_EXECUTOR_BINDING: frozenset({"local:artifact:read"}),
    CSV_COLUMN_SELECT_EXECUTOR_BINDING: frozenset(
        {"local:artifact:read", "local:artifact:write"}
    ),
    CSV_DESCRIPTIVE_SUMMARY_EXECUTOR_BINDING: frozenset(
        {"local:artifact:read", "local:artifact:write"}
    ),
    "ict.local.csv_manifest_preflight": frozenset(
        {"local:artifact:read", "local:artifact:write"}
    ),
    **LOCAL_FOLDER_EXECUTOR_PERMISSION_CAPABILITIES,
}


def _load_existing_checker():
    """Load ICT's existing checker from the repository's bundled desktop package."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    desktop_root = (
        Path(frozen_root) / "desktop"
        if isinstance(frozen_root, str)
        else Path(__file__).resolve().parents[3] / "desktop"
    )
    if not desktop_root.is_dir():
        raise WorkflowNodeFailure("LOCAL_CHECKER_UNAVAILABLE", "本机 CSV 检查器未安装。")
    root_string = str(desktop_root)
    if root_string not in sys.path:
        sys.path.insert(0, root_string)
    try:
        return importlib.import_module("ict_desktop.manifest_quality")
    except ImportError as error:
        logger.exception("local_csv_checker_import_failed error_type=%s", type(error).__name__)
        raise WorkflowNodeFailure("LOCAL_CHECKER_UNAVAILABLE", "本机 CSV 检查器未安装。") from error


def resolve_local_dependency_versions() -> dict[str, str]:
    """Report only bundled dependencies whose required API is importable."""
    try:
        checker = _load_existing_checker()
    except WorkflowNodeFailure:
        return {}
    installed_version = getattr(checker, "ICT_COMPONENT_DEPENDENCY_VERSION", None)
    if (
        not callable(getattr(checker, "inspect_manifest", None))
        or not isinstance(getattr(checker, "ManifestQualityError", None), type)
        or not isinstance(installed_version, str)
        or not installed_version.strip()
    ):
        logger.error(
            "local_csv_dependency_contract_unavailable dependency_id=%s",
            CSV_PREFLIGHT_DEPENDENCY_ID,
        )
        return {}
    return {CSV_PREFLIGHT_DEPENDENCY_ID: installed_version.strip()}


def local_csv_implementation_digest() -> str | None:
    """Fingerprint CSV executors, derived-artifact storage, and the ICT-owned checker."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if isinstance(frozen_root, str):
        bundle_root = Path(frozen_root)
        source_paths = (
            bundle_root / "app" / "services" / "local_csv_executor.py",
            bundle_root / "app" / "services" / "local_artifacts.py",
            bundle_root / "desktop" / "ict_desktop" / "manifest_quality.py",
        )
    else:
        source_paths = (
            Path(__file__).resolve(),
            Path(__file__).resolve().with_name("local_artifacts.py"),
            Path(__file__).resolve().parents[3] / "desktop" / "ict_desktop" / "manifest_quality.py",
        )
    try:
        digest = hashlib.sha256()
        for path in source_paths:
            path = path.resolve()
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
        return digest.hexdigest()
    except OSError:
        logger.exception("local_csv_executor_digest_unavailable")
        return None


def _artifact_id_from_node(node: dict[str, Any], inputs: dict[str, Any]) -> str:
    parameters = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
    raw_value = parameters.get("artifact_id") or inputs.get("csv") or inputs.get("manifest")
    if isinstance(raw_value, ArtifactHandle):
        raw_value = raw_value.artifact_id
    elif isinstance(raw_value, dict):
        raw_value = raw_value.get("artifact_id")
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise WorkflowNodeFailure("CSV_ARTIFACT_REQUIRED", "请选择已导入到本机的 CSV 产物。")
    return raw_value.strip()


def _normalize_csv_headers(
    headers: list[str],
    *,
    node_id: str,
    artifact_id: str,
) -> list[str]:
    """Match preflight's trimmed header names without changing data-cell values."""
    normalized = [header.strip() for header in headers]
    if not normalized or any(not header for header in normalized):
        logger.warning(
            "local_csv_header_invalid node_id=%s artifact_id=%s header_count=%s",
            node_id,
            artifact_id,
            len(headers),
        )
        raise WorkflowNodeFailure("CSV_HEADER_INVALID", "CSV 字段行包含空字段名。")
    if len(set(normalized)) != len(normalized):
        logger.warning(
            "local_csv_header_duplicate node_id=%s artifact_id=%s header_count=%s",
            node_id,
            artifact_id,
            len(headers),
        )
        raise WorkflowNodeFailure("CSV_HEADER_DUPLICATE", "CSV 字段行包含重复字段名。")
    return normalized


def _resolve_authorized_csv(
    artifact_id: str,
    artifact_store: LocalArtifactStore,
):
    """Resolve only a registered, authorized CSV handle from the local store."""
    try:
        resolved = artifact_store.resolve(artifact_id)
    except LocalArtifactError as error:
        raise WorkflowNodeFailure(error.code, str(error)) from error
    if resolved.handle.media_type != "text/csv":
        raise WorkflowNodeFailure("ARTIFACT_CSV_REQUIRED", "此节点只接受已导入的本机 CSV 产物。")
    if resolved.handle.authorization_status not in {"confirmed", "derived_from_confirmed_input"}:
        raise WorkflowNodeFailure("ARTIFACT_AUTHORIZATION_REQUIRED", "本机 CSV 产物缺少有效授权记录。")
    return resolved


def _resolve_csv_artifact_reference_sync(
    node: dict[str, Any],
    artifact_store: LocalArtifactStore,
) -> dict[str, dict[str, str | int]]:
    artifact_id = _artifact_id_from_node(node, {})
    resolved = _resolve_authorized_csv(artifact_id, artifact_store)
    logger.info(
        "local_csv_artifact_reference_resolved node_id=%s artifact_id=%s sha256=%s size_bytes=%s",
        node.get("id"),
        resolved.handle.artifact_id,
        resolved.handle.sha256,
        resolved.handle.size_bytes,
    )
    # Pass only the durable handle; file bytes stay in the local content store.
    return {"csv": resolved.handle.to_dict()}


async def run_local_csv_artifact_reference(
    node: dict[str, Any],
    artifact_store: LocalArtifactStore,
) -> dict[str, dict[str, str | int]]:
    """Expose a confirmed local CSV ArtifactHandle as a typed workflow output."""
    return await asyncio.to_thread(_resolve_csv_artifact_reference_sync, node, artifact_store)


def _selected_column_names(node: dict[str, Any]) -> list[str]:
    parameters = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
    raw_columns = parameters.get("columns")
    if not isinstance(raw_columns, str) or not raw_columns.strip():
        raise WorkflowNodeFailure("CSV_COLUMNS_REQUIRED", "请填写要保留的 CSV 字段名。")
    columns = [column.strip() for column in raw_columns.split(",")]
    if any(not column for column in columns):
        raise WorkflowNodeFailure(
            "CSV_COLUMNS_INVALID", "字段名不能为空；请使用逗号分隔字段名。"
        )
    if len(set(columns)) != len(columns):
        raise WorkflowNodeFailure("CSV_COLUMNS_DUPLICATE", "字段列表中有重复名称。")
    return columns


def _run_csv_column_selection_sync(
    node: dict[str, Any],
    inputs: dict[str, Any],
    artifact_store: LocalArtifactStore,
) -> dict[str, dict[str, str | int]]:
    artifact_id = _artifact_id_from_node(node, inputs)
    resolved = _resolve_authorized_csv(artifact_id, artifact_store)
    columns = _selected_column_names(node)

    # Verify the stored input before deriving another content-addressed artifact.
    input_digest = hashlib.sha256()
    try:
        with resolved.path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                input_digest.update(chunk)
    except OSError as error:
        logger.exception(
            "local_csv_column_select_input_read_failed node_id=%s artifact_id=%s",
            node.get("id"), resolved.handle.artifact_id,
        )
        raise WorkflowNodeFailure("CSV_READ_FAILED", "本机 CSV 无法读取。") from error
    if input_digest.hexdigest() != resolved.handle.sha256:
        raise WorkflowNodeFailure(
            "ARTIFACT_CONTENT_HASH_MISMATCH",
            "CSV 内容与导入时记录的 SHA-256 不一致，请重新导入。",
        )

    temporary_path: Path | None = None
    row_count = 0
    try:
        with resolved.path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source)
            try:
                headers = next(reader)
            except StopIteration as error:
                raise WorkflowNodeFailure("CSV_HEADER_EMPTY", "CSV 文件没有字段行。") from error

            headers = _normalize_csv_headers(
                headers,
                node_id=str(node.get("id") or "unknown"),
                artifact_id=resolved.handle.artifact_id,
            )

            header_indexes = {name: index for index, name in enumerate(headers)}
            missing_columns = [name for name in columns if name not in header_indexes]
            if missing_columns:
                logger.warning(
                    "local_csv_column_select_missing_columns node_id=%s artifact_id=%s missing_count=%s",
                    node.get("id"), resolved.handle.artifact_id, len(missing_columns),
                )
                raise WorkflowNodeFailure(
                    "CSV_COLUMNS_NOT_FOUND", "有字段名不在 CSV 中，请核对字段拼写。"
                )
            selected_indexes = [header_indexes[name] for name in columns]

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                prefix="select-columns-",
                suffix=".part",
                dir=artifact_store.temp_dir,
                delete=False,
            ) as destination:
                temporary_path = Path(destination.name)
                writer = csv.writer(destination)
                writer.writerow(columns)
                for row in reader:
                    if len(row) != len(headers):
                        logger.warning(
                            "local_csv_column_select_row_width_mismatch node_id=%s artifact_id=%s line_num=%s expected=%s actual=%s",
                            node.get("id"), resolved.handle.artifact_id, reader.line_num,
                            len(headers), len(row),
                        )
                        raise WorkflowNodeFailure(
                            "CSV_ROW_WIDTH_MISMATCH", "CSV 数据行字段数量不一致，未生成派生产物。"
                        )
                    writer.writerow([row[index] for index in selected_indexes])
                    row_count += 1
                destination.flush()
                os.fsync(destination.fileno())

        output_name = f"{Path(resolved.handle.file_name).stem[:160]}-selected.csv"
        try:
            with temporary_path.open("rb") as output:
                selected_handle = artifact_store.store_derived_csv(
                    output,
                    file_name=output_name,
                    source_artifact_id=resolved.handle.artifact_id,
                    producer_node_id=str(node.get("id") or "unknown"),
                    producer_run_id=(
                        str(node.get("_runtime_run_id"))
                        if isinstance(node.get("_runtime_run_id"), str)
                        else None
                    ),
                )
        except LocalArtifactError as error:
            raise WorkflowNodeFailure(error.code, str(error)) from error
    except WorkflowNodeFailure:
        raise
    except UnicodeDecodeError as error:
        logger.warning(
            "local_csv_column_select_encoding_rejected node_id=%s artifact_id=%s",
            node.get("id"), resolved.handle.artifact_id,
        )
        raise WorkflowNodeFailure("CSV_ENCODING_INVALID", "CSV 必须使用 UTF-8 编码。") from error
    except csv.Error as error:
        logger.exception(
            "local_csv_column_select_parse_failed node_id=%s artifact_id=%s",
            node.get("id"), resolved.handle.artifact_id,
        )
        raise WorkflowNodeFailure("CSV_PARSE_FAILED", "CSV 格式无法解析。") from error
    except OSError as error:
        logger.exception(
            "local_csv_column_select_write_failed node_id=%s artifact_id=%s",
            node.get("id"), resolved.handle.artifact_id,
        )
        raise WorkflowNodeFailure("CSV_WRITE_FAILED", "本机派生 CSV 写入失败。") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    logger.info(
        "local_csv_columns_selected node_id=%s source_artifact_id=%s output_artifact_id=%s input_sha256=%s column_count=%s row_count=%s",
        node.get("id"), resolved.handle.artifact_id, selected_handle.artifact_id,
        resolved.handle.sha256, len(columns), row_count,
    )
    return {"selected_csv": selected_handle.to_dict()}


async def run_local_csv_column_selection(
    node: dict[str, Any],
    inputs: dict[str, Any],
    artifact_store: LocalArtifactStore,
) -> dict[str, dict[str, str | int]]:
    """Select declared CSV fields off the scheduler event loop and return a handle."""
    return await asyncio.to_thread(_run_csv_column_selection_sync, node, inputs, artifact_store)


def _run_csv_descriptive_summary_sync(
    node: dict[str, Any],
    inputs: dict[str, Any],
    artifact_store: LocalArtifactStore,
) -> dict[str, dict[str, str | int]]:
    """Stream a bounded exploratory summary without retaining CSV rows in memory."""
    artifact_id = _artifact_id_from_node(node, inputs)
    resolved = _resolve_authorized_csv(artifact_id, artifact_store)

    input_digest = hashlib.sha256()
    try:
        with resolved.path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                input_digest.update(chunk)
    except OSError as error:
        logger.exception(
            "local_csv_summary_input_read_failed node_id=%s artifact_id=%s",
            node.get("id"), resolved.handle.artifact_id,
        )
        raise WorkflowNodeFailure("CSV_READ_FAILED", "本机 CSV 无法读取。") from error
    if input_digest.hexdigest() != resolved.handle.sha256:
        raise WorkflowNodeFailure(
            "ARTIFACT_CONTENT_HASH_MISMATCH",
            "CSV 内容与导入时记录的 SHA-256 不一致，请重新导入。",
        )

    row_count = 0
    total_tracked_categories = 0
    column_states: list[dict[str, Any]] = []
    try:
        with resolved.path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source)
            try:
                headers = next(reader)
            except StopIteration as error:
                raise WorkflowNodeFailure("CSV_HEADER_EMPTY", "CSV 文件没有字段行。") from error

            if len(headers) > CSV_SUMMARY_MAX_COLUMNS:
                raise WorkflowNodeFailure(
                    "CSV_COLUMN_LIMIT_EXCEEDED", "CSV 字段数量超过本机摘要处理上限。"
                )
            headers = _normalize_csv_headers(
                headers,
                node_id=str(node.get("id") or "unknown"),
                artifact_id=resolved.handle.artifact_id,
            )

            column_states = [
                {
                    "name": header,
                    "missing_count": 0,
                    "non_missing_count": 0,
                    "numeric_candidate": True,
                    "numeric_min": None,
                    "numeric_max": None,
                    "numeric_mean": 0.0,
                    "category_counts": Counter(),
                    "category_summary_truncated": False,
                }
                for header in headers
            ]

            for row in reader:
                if len(row) != len(headers):
                    logger.warning(
                        "local_csv_summary_row_width_mismatch node_id=%s artifact_id=%s line_num=%s expected=%s actual=%s",
                        node.get("id"), resolved.handle.artifact_id, reader.line_num,
                        len(headers), len(row),
                    )
                    raise WorkflowNodeFailure(
                        "CSV_ROW_WIDTH_MISMATCH", "CSV 数据行字段数量不一致，无法生成摘要。"
                    )
                row_count += 1
                for state, raw_value in zip(column_states, row, strict=True):
                    value = raw_value.strip()
                    if not value:
                        state["missing_count"] += 1
                        continue

                    state["non_missing_count"] += 1
                    try:
                        numeric_value = float(value)
                    except ValueError:
                        state["numeric_candidate"] = False
                        numeric_value = None
                    if numeric_value is not None:
                        if not math.isfinite(numeric_value):
                            state["numeric_candidate"] = False
                        else:
                            count = state["non_missing_count"]
                            state["numeric_min"] = numeric_value if state["numeric_min"] is None else min(state["numeric_min"], numeric_value)
                            state["numeric_max"] = numeric_value if state["numeric_max"] is None else max(state["numeric_max"], numeric_value)
                            previous_mean = state["numeric_mean"]
                            state["numeric_mean"] = previous_mean * ((count - 1) / count) + numeric_value / count

                    counts: Counter[str] = state["category_counts"]
                    if state["category_summary_truncated"]:
                        continue
                    if value in counts:
                        counts[value] += 1
                    elif (
                        len(value) > CSV_SUMMARY_CATEGORY_VALUE_LIMIT
                        or len(counts) >= CSV_SUMMARY_CATEGORY_LIMIT
                        or total_tracked_categories >= CSV_SUMMARY_TOTAL_CATEGORY_LIMIT
                    ):
                        total_tracked_categories -= len(counts)
                        counts.clear()
                        state["category_summary_truncated"] = True
                    else:
                        counts[value] = 1
                        total_tracked_categories += 1
    except WorkflowNodeFailure:
        raise
    except UnicodeDecodeError as error:
        logger.warning(
            "local_csv_summary_encoding_rejected node_id=%s artifact_id=%s",
            node.get("id"), resolved.handle.artifact_id,
        )
        raise WorkflowNodeFailure("CSV_ENCODING_INVALID", "CSV 必须使用 UTF-8 编码。") from error
    except csv.Error as error:
        logger.exception(
            "local_csv_summary_parse_failed node_id=%s artifact_id=%s",
            node.get("id"), resolved.handle.artifact_id,
        )
        raise WorkflowNodeFailure("CSV_PARSE_FAILED", "CSV 格式无法解析。") from error
    except OSError as error:
        logger.exception(
            "local_csv_summary_read_failed node_id=%s artifact_id=%s",
            node.get("id"), resolved.handle.artifact_id,
        )
        raise WorkflowNodeFailure("CSV_READ_FAILED", "本机 CSV 无法读取。") from error

    summarized_columns: list[dict[str, Any]] = []
    for state in column_states:
        missing_count = state["missing_count"]
        non_missing_count = state["non_missing_count"]
        missing_rate = missing_count / row_count if row_count else 0.0
        if non_missing_count == 0:
            column_kind = "all_missing"
            numeric_summary = None
            category_summary = None
        elif state["numeric_candidate"]:
            column_kind = "numeric"
            numeric_summary = {
                "minimum": state["numeric_min"],
                "maximum": state["numeric_max"],
                "mean": state["numeric_mean"],
            }
            category_summary = None
        else:
            column_kind = "categorical"
            numeric_summary = None
            if state["category_summary_truncated"]:
                category_summary = {
                    "distinct_value_count": None,
                    "top_values": [],
                    "truncated": True,
                }
            else:
                counts = state["category_counts"]
                category_summary = {
                    "distinct_value_count": len(counts),
                    "top_values": [
                        {"value": value, "count": count}
                        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]
                    ],
                    "truncated": False,
                }
        summarized_columns.append({
            "name": state["name"][:CSV_SUMMARY_CATEGORY_VALUE_LIMIT],
            "kind": column_kind,
            "row_count": row_count,
            "missing_count": missing_count,
            "missing_rate": missing_rate,
            "numeric_summary": numeric_summary,
            "category_summary": category_summary,
        })

    payload = {
        "report_type": "csv_descriptive_summary",
        "label": "探索性描述统计摘要，非科研结论",
        "research_result": False,
        "summary_method": "ict.csv-descriptive-summary.v1",
        "missing_definition": "仅将去除首尾空白后为空的单元格视为缺失；NA、N/A 等文本按原值保留。",
        "input": {
            "artifact_id": resolved.handle.artifact_id,
            "sha256": resolved.handle.sha256,
            "size_bytes": resolved.handle.size_bytes,
            "provenance": resolved.handle.provenance,
            "authorization_status": resolved.handle.authorization_status,
        },
        "row_count": row_count,
        "column_count": len(headers),
        "columns": summarized_columns,
        "limitations": [
            "本摘要仅描述当前 CSV 的字段、空白单元格和取值分布，不验证数据真实性、实验设计、抽样偏倚或因果关系。",
            "数值字段按有限浮点数解析；摘要不包含假设检验、置信区间或科研结论。",
            "类别频数最多追踪每列 500 个、全表 5,000 个不同值；类别值超过 256 字符或触及上限时，该列频数将省略。",
        ],
    }
    try:
        report_handle = artifact_store.store_json_report(
            payload,
            producer_node_id=str(node.get("id") or "unknown"),
            producer_run_id=(
                str(node.get("_runtime_run_id"))
                if isinstance(node.get("_runtime_run_id"), str)
                else None
            ),
            file_name="csv-descriptive-summary.json",
        )
    except LocalArtifactError as error:
        raise WorkflowNodeFailure(error.code, str(error)) from error

    logger.info(
        "local_csv_summary_completed node_id=%s artifact_id=%s input_sha256=%s row_count=%s column_count=%s",
        node.get("id"), report_handle.artifact_id, resolved.handle.sha256, row_count, len(headers),
    )
    return {"summary_report": report_handle.to_dict()}


async def run_local_csv_descriptive_summary(
    node: dict[str, Any],
    inputs: dict[str, Any],
    artifact_store: LocalArtifactStore,
) -> dict[str, dict[str, str | int]]:
    """Run a deterministic local CSV summary away from the scheduler event loop."""
    return await asyncio.to_thread(_run_csv_descriptive_summary_sync, node, inputs, artifact_store)


def _run_preflight_sync(
    node: dict[str, Any],
    inputs: dict[str, Any],
    artifact_store: LocalArtifactStore,
) -> dict[str, dict[str, str | int]]:
    checker = _load_existing_checker()
    artifact_id = _artifact_id_from_node(node, inputs)
    resolved = _resolve_authorized_csv(artifact_id, artifact_store)

    try:
        report = checker.inspect_manifest(resolved.path)
    except checker.ManifestQualityError as error:
        logger.warning(
            "local_csv_preflight_rejected node_id=%s artifact_id=%s error_code=%s",
            node.get("id"),
            resolved.handle.artifact_id,
            error.code,
        )
        raise WorkflowNodeFailure(error.code, str(error)) from error
    if report.sha256 != resolved.handle.sha256:
        raise WorkflowNodeFailure(
            "ARTIFACT_CONTENT_HASH_MISMATCH",
            "CSV 内容与导入时记录的 SHA-256 不一致，请重新导入。",
        )

    issue_rows = [asdict(issue) for issue in report.issues]
    payload = {
        "report_type": "csv_manifest_structural_preflight",
        "label": "结构预检，非科研结果",
        "research_result": False,
        "rule_set_version": "ict.csv-manifest-structure.v1",
        "status": report.status,
        "input": {
            "artifact_id": resolved.handle.artifact_id,
            "sha256": resolved.handle.sha256,
            "size_bytes": resolved.handle.size_bytes,
            "provenance": resolved.handle.provenance,
            "authorization_status": resolved.handle.authorization_status,
        },
        "row_count": report.row_count,
        "columns": list(report.columns),
        "split_counts": dict(report.split_counts),
        "label_category_count": report.label_category_count,
        "issues": issue_rows,
        "checker": "ict_desktop.manifest_quality.inspect_manifest",
        "checker_version": CSV_PREFLIGHT_EXECUTOR_VERSION,
    }
    try:
        report_handle = artifact_store.store_json_report(
            payload,
            producer_node_id=str(node.get("id") or "unknown"),
            producer_run_id=(
                str(node.get("_runtime_run_id"))
                if isinstance(node.get("_runtime_run_id"), str)
                else None
            ),
        )
    except LocalArtifactError as error:
        raise WorkflowNodeFailure(error.code, str(error)) from error
    logger.info(
        "local_csv_preflight_completed node_id=%s artifact_id=%s input_sha256=%s status=%s row_count=%s",
        node.get("id"),
        resolved.handle.artifact_id,
        resolved.handle.sha256,
        report.status,
        report.row_count,
    )
    return {"quality_report": report_handle.to_dict()}


async def run_local_csv_preflight(
    node: dict[str, Any],
    inputs: dict[str, Any],
    artifact_store: LocalArtifactStore,
) -> dict[str, dict[str, str | int]]:
    """Run the existing pure-Python CSV checker off the scheduler event loop."""
    return await asyncio.to_thread(_run_preflight_sync, node, inputs, artifact_store)


def build_local_executor_registry(artifact_store: LocalArtifactStore) -> dict[str, Any]:
    """Return the audited built-in local executor set; no dynamic module loading."""
    async def csv_artifact_source(node: dict[str, Any], _inputs: dict[str, Any]):
        return await run_local_csv_artifact_reference(node, artifact_store)

    async def csv_manifest_preflight(node: dict[str, Any], inputs: dict[str, Any]):
        return await run_local_csv_preflight(node, inputs, artifact_store)

    async def csv_select_columns(node: dict[str, Any], inputs: dict[str, Any]):
        return await run_local_csv_column_selection(node, inputs, artifact_store)

    async def csv_descriptive_summary(node: dict[str, Any], inputs: dict[str, Any]):
        return await run_local_csv_descriptive_summary(node, inputs, artifact_store)

    registry = {
        CSV_ARTIFACT_SOURCE_EXECUTOR_BINDING: csv_artifact_source,
        CSV_COLUMN_SELECT_EXECUTOR_BINDING: csv_select_columns,
        CSV_DESCRIPTIVE_SUMMARY_EXECUTOR_BINDING: csv_descriptive_summary,
        "ict.local.csv_manifest_preflight": csv_manifest_preflight,
    }
    registry.update(build_local_csv_folder_executor_registry(artifact_store))
    return registry
