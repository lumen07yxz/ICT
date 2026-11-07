"""Offline CSV folder source and per-file quality checker for local workflows."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import logging
import math
import sqlite3
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

from app.services.local_artifacts import ArtifactHandle, LocalArtifactError, LocalArtifactStore
from app.services.workflow_scheduler import WorkflowNodeFailure


logger = logging.getLogger("ict.local_runtime.csv_folder")

CSV_FOLDER_SOURCE_EXECUTOR_BINDING = "ict.local.csv_folder_source"
CSV_FOLDER_SOURCE_EXECUTOR_VERSION = "1.0.0"
CSV_FOLDER_QUALITY_EXECUTOR_BINDING = "ict.local.csv_folder_quality_check"
CSV_FOLDER_QUALITY_EXECUTOR_VERSION = "1.0.0"
CSV_FOLDER_QUALITY_RULESET_VERSION = "ict.csv-folder-quality.v1"
CSV_FOLDER_MAX_FILES = 200
CSV_FOLDER_MAX_BYTES = 100 * 1024 * 1024
CSV_FOLDER_MANIFEST_MAX_CHARS = 200_000

LOCAL_FOLDER_EXECUTOR_PERMISSION_CAPABILITIES = {
    CSV_FOLDER_SOURCE_EXECUTOR_BINDING: frozenset({"local:artifact:read"}),
    CSV_FOLDER_QUALITY_EXECUTOR_BINDING: frozenset({"local:artifact:read", "local:artifact:write"}),
}


class CsvFolderInputError(ValueError):
    """A folder selection or member handle failed a stable local validation rule."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def csv_folder_implementation_digest() -> str | None:
    """Bind the executor contract to this reviewed implementation file."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if isinstance(frozen_root, str):
        bundle_root = Path(frozen_root)
        source_paths = (
            bundle_root / "app" / "services" / "local_csv_folder_executor.py",
            bundle_root / "app" / "services" / "local_artifacts.py",
        )
    else:
        source_paths = (Path(__file__).resolve(), Path(__file__).resolve().with_name("local_artifacts.py"))
    try:
        digest = hashlib.sha256()
        for path in source_paths:
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
        return digest.hexdigest()
    except OSError:
        logger.exception("local_csv_folder_executor_digest_unavailable")
        return None


def _safe_relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise CsvFolderInputError("CSV_FOLDER_PATH_INVALID", "文件夹中包含无效文件路径。")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or len(normalized) > 500
        or any(part in {"", ".", ".."} for part in normalized.split("/"))
        or (path.parts and ":" in path.parts[0])
        or path.suffix.casefold() != ".csv"
    ):
        raise CsvFolderInputError("CSV_FOLDER_PATH_INVALID", "文件夹内 CSV 相对路径无效。")
    return path.as_posix()


def _verify_handle(
    item: dict[str, Any],
    artifact_store: LocalArtifactStore,
    *,
    verify_content: bool,
) -> tuple[dict[str, Any], Path]:
    artifact_id = item.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise CsvFolderInputError("ARTIFACT_NOT_FOUND", "文件夹清单缺少本机 CSV 产物 ID。")
    try:
        resolved = artifact_store.resolve(artifact_id)
    except LocalArtifactError as error:
        raise CsvFolderInputError(error.code, str(error)) from error
    handle = resolved.handle
    if handle.media_type != "text/csv" or Path(handle.file_name).suffix.casefold() != ".csv":
        raise CsvFolderInputError("ARTIFACT_CSV_REQUIRED", "文件夹只允许引用已导入的 CSV 产物。")
    if handle.authorization_status not in {"confirmed", "derived_from_confirmed_input"}:
        raise CsvFolderInputError("ARTIFACT_AUTHORIZATION_REQUIRED", "文件夹中的 CSV 缺少本机处理授权。")
    if (
        item.get("sha256") != handle.sha256
        or item.get("size_bytes") != handle.size_bytes
        or handle.size_bytes < 1
        or handle.size_bytes > 100 * 1024 * 1024
    ):
        raise CsvFolderInputError("ARTIFACT_HANDLE_MISMATCH", "文件夹中的 CSV 产物信息与本机记录不匹配。")
    if verify_content:
        digest = hashlib.sha256()
        try:
            with resolved.path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as error:
            raise CsvFolderInputError("ARTIFACT_FILE_MISSING", "文件夹中的本机 CSV 无法读取。") from error
        if digest.hexdigest() != handle.sha256:
            raise CsvFolderInputError("ARTIFACT_CONTENT_HASH_MISMATCH", "CSV 文件内容与导入时的哈希不一致。")
    return (
        {
            "relative_path": _safe_relative_path(item.get("relative_path")),
            "artifact_id": handle.artifact_id,
            "sha256": handle.sha256,
            "size_bytes": handle.size_bytes,
            "file_name": handle.file_name,
            "provenance": handle.provenance,
            "authorization_status": handle.authorization_status,
        },
        resolved.path,
    )


def _parse_folder_manifest(node: dict[str, Any], artifact_store: LocalArtifactStore) -> dict[str, Any]:
    parameters = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
    encoded = parameters.get("files_json")
    if not isinstance(encoded, str) or not encoded or len(encoded) > CSV_FOLDER_MANIFEST_MAX_CHARS:
        raise CsvFolderInputError("CSV_FOLDER_MANIFEST_INVALID", "请在文件夹来源节点选择 CSV 文件夹。")
    try:
        manifest = json.loads(encoded)
    except json.JSONDecodeError as error:
        raise CsvFolderInputError("CSV_FOLDER_MANIFEST_INVALID", "CSV 文件夹清单格式无效，请重新选择目录。") from error
    if not isinstance(manifest, dict):
        raise CsvFolderInputError("CSV_FOLDER_MANIFEST_INVALID", "CSV 文件夹清单格式无效，请重新选择目录。")
    folder_name = manifest.get("folder_name")
    files = manifest.get("files")
    if (
        not isinstance(folder_name, str)
        or not folder_name.strip()
        or len(folder_name) > 120
        or folder_name in {".", ".."}
        or "/" in folder_name
        or "\\" in folder_name
        or ":" in folder_name
    ):
        raise CsvFolderInputError("CSV_FOLDER_MANIFEST_INVALID", "CSV 文件夹名称无效，请重新选择目录。")
    if not isinstance(files, list) or not files or len(files) > CSV_FOLDER_MAX_FILES:
        raise CsvFolderInputError("CSV_FOLDER_FILE_COUNT_INVALID", "目录必须包含 1 至 200 个 CSV 文件。")

    members: list[dict[str, Any]] = []
    resolved_paths: list[Path] = []
    seen_paths: set[str] = set()
    total_size = 0
    for raw_item in files:
        if not isinstance(raw_item, dict):
            raise CsvFolderInputError("CSV_FOLDER_MANIFEST_INVALID", "CSV 文件夹清单包含无效文件记录。")
        member, path = _verify_handle(raw_item, artifact_store, verify_content=True)
        normalized_path = member["relative_path"]
        if PurePosixPath(normalized_path).parts[0] != folder_name:
            raise CsvFolderInputError("CSV_FOLDER_PATH_INVALID", "CSV 文件夹内相对路径未归属到所选目录。")
        path_key = normalized_path.casefold()
        if path_key in seen_paths:
            raise CsvFolderInputError("CSV_FOLDER_PATH_DUPLICATE", "CSV 文件夹清单包含重复的相对路径。")
        seen_paths.add(path_key)
        total_size += member["size_bytes"]
        if total_size > CSV_FOLDER_MAX_BYTES:
            raise CsvFolderInputError("CSV_FOLDER_SIZE_LIMIT_EXCEEDED", "CSV 文件夹总大小超过本机 100 MiB 限制。")
        members.append(member)
        resolved_paths.append(path)

    canonical = {
        "folder_name": folder_name,
        "files": [
            {key: item[key] for key in ("relative_path", "artifact_id", "sha256", "size_bytes")}
            for item in members
        ],
    }
    collection_sha256 = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "collection_sha256": collection_sha256,
        "folder_name": folder_name,
        "file_count": len(members),
        "total_size_bytes": total_size,
        "ignored_file_count": min(100_000, _safe_nonnegative_int(manifest.get("ignored_file_count"))),
        "files": members,
        "_paths": resolved_paths,
    }


def _safe_nonnegative_int(value: Any) -> int:
    return value if type(value) is int and value >= 0 else 0


async def run_csv_folder_source(
    node: dict[str, Any],
    _inputs: dict[str, Any],
    artifact_store: LocalArtifactStore,
) -> dict[str, Any]:
    """Resolve a selected directory manifest into a small typed collection handle."""
    try:
        manifest = await asyncio.to_thread(_parse_folder_manifest, node, artifact_store)
    except CsvFolderInputError as error:
        logger.warning(
            "local_csv_folder_source_rejected node_id=%s error_code=%s",
            node.get("id"), error.code,
        )
        raise WorkflowNodeFailure(error.code, str(error)) from error
    logger.info(
        "local_csv_folder_source_resolved node_id=%s folder_file_count=%s total_size_bytes=%s collection_sha256=%s ignored_file_count=%s",
        node.get("id"), manifest["file_count"], manifest["total_size_bytes"],
        manifest["collection_sha256"], manifest["ignored_file_count"],
    )
    return {"files": {key: value for key, value in manifest.items() if not key.startswith("_")}}


def _split_rule_columns(value: Any, parameter_name: str) -> list[str]:
    if value is None or value == "":
        return []
    if not isinstance(value, str):
        raise CsvFolderInputError("CSV_QUALITY_RULE_INVALID", f"规则“{parameter_name}”必须使用逗号分隔的字段名。")
    columns = [part.strip() for part in value.split(",") if part.strip()]
    if len(columns) > 100 or any(len(part) > 180 for part in columns):
        raise CsvFolderInputError("CSV_QUALITY_RULE_INVALID", f"规则“{parameter_name}”包含过多或过长的字段名。")
    if len({column.casefold() for column in columns}) != len(columns):
        raise CsvFolderInputError("CSV_QUALITY_RULE_INVALID", f"规则“{parameter_name}”包含重复字段名。")
    return columns


def _parse_quality_rules(parameters: dict[str, Any]) -> dict[str, Any]:
    required_columns = _split_rule_columns(parameters.get("required_columns", ""), "必需字段")
    unique_key_columns = _split_rule_columns(parameters.get("unique_key_columns", ""), "唯一键字段")
    raw_rate = parameters.get("max_missing_rate", "0.05")
    try:
        max_missing_rate = float(raw_rate)
    except (TypeError, ValueError) as error:
        raise CsvFolderInputError("CSV_QUALITY_RULE_INVALID", "缺失率阈值必须是 0 到 1 之间的小数。") from error
    if not math.isfinite(max_missing_rate) or max_missing_rate < 0 or max_missing_rate > 1:
        raise CsvFolderInputError("CSV_QUALITY_RULE_INVALID", "缺失率阈值必须是 0 到 1 之间的小数。")
    return {
        "required_columns": required_columns,
        "unique_key_columns": unique_key_columns,
        "max_missing_rate": max_missing_rate,
    }


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_one_csv(
    member: dict[str, Any],
    path: Path,
    rules: dict[str, Any],
    artifact_store: LocalArtifactStore,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "relative_path": member["relative_path"],
        "artifact_id": member["artifact_id"],
        "sha256": member["sha256"],
        "size_bytes": member["size_bytes"],
        "row_count": 0,
        "column_count": 0,
        "columns": [],
        "missing_counts": [],
        "duplicate_key_count": 0,
        "status": "blocked",
        "issues": issues,
    }
    temp_db_path: Path | None = None
    key_db: sqlite3.Connection | None = None
    try:
        if _hash_file(path) != member["sha256"]:
            raise CsvFolderInputError("ARTIFACT_CONTENT_HASH_MISMATCH", "CSV 文件内容与导入时的哈希不一致。")
        resolved = artifact_store.resolve(member["artifact_id"])
        if resolved.handle.authorization_status not in {"confirmed", "derived_from_confirmed_input"}:
            raise CsvFolderInputError("ARTIFACT_AUTHORIZATION_REQUIRED", "CSV 缺少有效的本机处理授权。")

        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            raw_header = next(reader, None)
            if not raw_header:
                raise CsvFolderInputError("CSV_HEADER_MISSING", "CSV 没有有效的表头行。")
            columns = [value.strip() for value in raw_header]
            if any(not column for column in columns):
                raise CsvFolderInputError("CSV_HEADER_INVALID", "CSV 包含空字段名。")
            if len({column.casefold() for column in columns}) != len(columns):
                raise CsvFolderInputError("CSV_HEADER_DUPLICATE", "CSV 包含重复字段名。")
            if len(columns) > 500:
                raise CsvFolderInputError("CSV_COLUMN_LIMIT_EXCEEDED", "CSV 字段数超过本机质量检查上限。")
            result["columns"] = columns
            result["column_count"] = len(columns)
            column_indexes = {column: index for index, column in enumerate(columns)}
            required_missing = [column for column in rules["required_columns"] if column not in column_indexes]
            key_missing = [column for column in rules["unique_key_columns"] if column not in column_indexes]
            if required_missing:
                issues.append({"code": "REQUIRED_COLUMNS_MISSING", "severity": "blocker", "count": len(required_missing), "fields": required_missing})
            if key_missing:
                issues.append({"code": "UNIQUE_KEY_COLUMNS_MISSING", "severity": "blocker", "count": len(key_missing), "fields": key_missing})

            missing_counts = [0] * len(columns)
            unique_indexes = [column_indexes[column] for column in rules["unique_key_columns"] if column in column_indexes]
            if unique_indexes and not key_missing:
                with tempfile.NamedTemporaryFile(prefix="csv-key-check-", suffix=".sqlite3", dir=artifact_store.temp_dir, delete=False) as temporary:
                    temp_db_path = Path(temporary.name)
                key_db = sqlite3.connect(temp_db_path)
                key_db.execute("CREATE TABLE seen_keys (key_hash TEXT PRIMARY KEY)")

            row_width_mismatches = 0
            duplicate_key_count = 0
            for row in reader:
                result["row_count"] += 1
                if len(row) != len(columns):
                    row_width_mismatches += 1
                for index in range(len(columns)):
                    if index >= len(row) or not row[index].strip():
                        missing_counts[index] += 1
                if key_db is not None and all(index < len(row) and row[index].strip() for index in unique_indexes):
                    key_values = [row[index].strip() for index in unique_indexes]
                    key_hash = hashlib.sha256(
                        json.dumps(key_values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    ).hexdigest()
                    cursor = key_db.execute("INSERT OR IGNORE INTO seen_keys(key_hash) VALUES (?)", (key_hash,))
                    if cursor.rowcount == 0:
                        duplicate_key_count += 1
            if key_db is not None:
                key_db.commit()

            result["missing_counts"] = [
                {
                    "field": column,
                    "count": missing_counts[index],
                    "rate": missing_counts[index] / result["row_count"] if result["row_count"] else 0.0,
                }
                for index, column in enumerate(columns)
            ]
            result["duplicate_key_count"] = duplicate_key_count
            if row_width_mismatches:
                issues.append({"code": "CSV_ROW_WIDTH_MISMATCH", "severity": "blocker", "count": row_width_mismatches, "fields": []})
            if duplicate_key_count:
                issues.append({"code": "DUPLICATE_UNIQUE_KEY", "severity": "blocker", "count": duplicate_key_count, "fields": rules["unique_key_columns"]})
            high_missing = [
                item for item in result["missing_counts"]
                if item["rate"] > rules["max_missing_rate"]
            ]
            if high_missing:
                issues.append({
                    "code": "MISSING_RATE_EXCEEDED",
                    "severity": "warning",
                    "count": sum(item["count"] for item in high_missing),
                    "fields": [item["field"] for item in high_missing],
                })
            result["status"] = (
                "blocked" if any(issue["severity"] == "blocker" for issue in issues)
                else "warning" if issues
                else "passed"
            )
    except CsvFolderInputError as error:
        result["issues"].append({"code": error.code, "severity": "blocker", "count": 1, "fields": []})
        result["status"] = "blocked"
    except LocalArtifactError as error:
        result["issues"].append({"code": error.code, "severity": "blocker", "count": 1, "fields": []})
        result["status"] = "blocked"
    except UnicodeDecodeError:
        result["issues"].append({"code": "CSV_ENCODING_UNSUPPORTED", "severity": "blocker", "count": 1, "fields": []})
        result["status"] = "blocked"
    except csv.Error:
        result["issues"].append({"code": "CSV_PARSE_ERROR", "severity": "blocker", "count": 1, "fields": []})
        result["status"] = "blocked"
    except (OSError, sqlite3.Error):
        logger.exception("local_csv_folder_file_check_failed artifact_id=%s", member["artifact_id"])
        result["issues"].append({"code": "LOCAL_FILE_CHECK_FAILED", "severity": "blocker", "count": 1, "fields": []})
        result["status"] = "blocked"
    finally:
        if key_db is not None:
            key_db.close()
        if temp_db_path is not None:
            try:
                temp_db_path.unlink(missing_ok=True)
            except OSError:
                logger.exception("local_csv_folder_key_index_cleanup_failed")
    return result


def _iter_collection_members(collection: Any) -> Iterator[dict[str, Any]]:
    if not isinstance(collection, dict) or not isinstance(collection.get("files"), list):
        raise CsvFolderInputError("CSV_FOLDER_INPUT_INVALID", "质量检查节点没有收到有效的 CSV 文件夹输入。")
    for item in collection["files"]:
        if not isinstance(item, dict):
            raise CsvFolderInputError("CSV_FOLDER_INPUT_INVALID", "CSV 文件夹输入包含无效文件记录。")
        yield item


def _run_folder_quality_check_sync(
    node: dict[str, Any],
    inputs: dict[str, Any],
    artifact_store: LocalArtifactStore,
) -> dict[str, Any]:
    parameters = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
    try:
        rules = _parse_quality_rules(parameters)
        collection = inputs.get("files")
        if not isinstance(collection, dict) or collection.get("collection_sha256") is None:
            raise CsvFolderInputError("CSV_FOLDER_INPUT_INVALID", "质量检查节点没有收到有效的 CSV 文件夹输入。")
        members = list(_iter_collection_members(collection))
        if not members or len(members) > CSV_FOLDER_MAX_FILES:
            raise CsvFolderInputError("CSV_FOLDER_FILE_COUNT_INVALID", "CSV 文件夹必须包含 1 至 200 个 CSV 文件。")
    except CsvFolderInputError as error:
        raise WorkflowNodeFailure(error.code, str(error)) from error

    total_size = sum(_safe_nonnegative_int(item.get("size_bytes")) for item in members)
    if total_size > CSV_FOLDER_MAX_BYTES:
        raise WorkflowNodeFailure("CSV_FOLDER_SIZE_LIMIT_EXCEEDED", "CSV 文件夹总大小超过本机 100 MiB 限制。")

    results: list[dict[str, Any]] = []
    for member in members:
        try:
            normalized, path = _verify_handle(member, artifact_store, verify_content=False)
            results.append(_check_one_csv(normalized, path, rules, artifact_store))
        except CsvFolderInputError as error:
            logger.warning(
                "local_csv_folder_member_rejected node_id=%s artifact_id=%s error_code=%s",
                node.get("id"), member.get("artifact_id"), error.code,
            )
            results.append({
                "relative_path": str(member.get("relative_path") or "未知路径"),
                "artifact_id": str(member.get("artifact_id") or ""),
                "sha256": str(member.get("sha256") or ""),
                "size_bytes": _safe_nonnegative_int(member.get("size_bytes")),
                "row_count": 0,
                "column_count": 0,
                "columns": [],
                "missing_counts": [],
                "duplicate_key_count": 0,
                "status": "blocked",
                "issues": [{"code": error.code, "severity": "blocker", "count": 1, "fields": []}],
            })

    blocked = sum(item["status"] == "blocked" for item in results)
    warning = sum(item["status"] == "warning" for item in results)
    overall_status = "blocked" if blocked else "warning" if warning else "passed"
    report = {
        "report_type": "csv_folder_quality_v1",
        "label": "本机 CSV 文件夹质量检查报告，非科研结果",
        "research_result": False,
        "rules_version": CSV_FOLDER_QUALITY_RULESET_VERSION,
        "collection": {
            "folder_name": collection.get("folder_name"),
            "collection_sha256": collection.get("collection_sha256"),
            "file_count": len(members),
            "ignored_file_count": _safe_nonnegative_int(collection.get("ignored_file_count")),
            "total_size_bytes": total_size,
        },
        "rules": {
            "required_columns": rules["required_columns"],
            "unique_key_columns": rules["unique_key_columns"],
            "max_missing_rate": rules["max_missing_rate"],
        },
        "summary": {
            "status": overall_status,
            "file_count": len(results),
            "passed_count": len(results) - blocked - warning,
            "warning_count": warning,
            "blocked_count": blocked,
        },
        "files": results,
    }
    try:
        report_handle = artifact_store.store_json_report(
            report,
            producer_node_id=str(node.get("id") or "unknown"),
            producer_run_id=(
                str(node.get("_runtime_run_id"))
                if isinstance(node.get("_runtime_run_id"), str)
                else None
            ),
            file_name="csv-folder-quality-report.json",
        )
    except LocalArtifactError as error:
        raise WorkflowNodeFailure(error.code, str(error)) from error
    logger.info(
        "local_csv_folder_quality_completed node_id=%s collection_sha256=%s file_count=%s status=%s blocked=%s warnings=%s report_artifact_id=%s",
        node.get("id"), collection.get("collection_sha256"), len(results), overall_status,
        blocked, warning, report_handle.artifact_id,
    )
    return {"quality_report": report_handle.to_dict(), "quality_status": overall_status}


async def run_csv_folder_quality_check(
    node: dict[str, Any],
    inputs: dict[str, Any],
    artifact_store: LocalArtifactStore,
) -> dict[str, Any]:
    """Stream the folder files off the event loop and persist one aggregate report."""
    return await asyncio.to_thread(_run_folder_quality_check_sync, node, inputs, artifact_store)


def build_local_csv_folder_executor_registry(artifact_store: LocalArtifactStore) -> dict[str, Any]:
    """Expose the reviewed folder executors without dynamic plugin loading."""
    async def csv_folder_source(node: dict[str, Any], inputs: dict[str, Any]):
        return await run_csv_folder_source(node, inputs, artifact_store)

    async def csv_folder_quality_check(node: dict[str, Any], inputs: dict[str, Any]):
        return await run_csv_folder_quality_check(node, inputs, artifact_store)

    return {
        CSV_FOLDER_SOURCE_EXECUTOR_BINDING: csv_folder_source,
        CSV_FOLDER_QUALITY_EXECUTOR_BINDING: csv_folder_quality_check,
    }
