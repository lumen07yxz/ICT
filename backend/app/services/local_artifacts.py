"""Content-addressed local artifact storage for offline workflow inputs/results."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from collections.abc import Iterator
from typing import BinaryIO
from urllib.parse import unquote, urlsplit
from uuid import UUID, uuid4


logger = logging.getLogger("ict.local_runtime.artifacts")


class LocalArtifactError(ValueError):
    """Safe local artifact error with a stable code and no source path in its text."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ArtifactHandle:
    """Small durable reference passed between nodes instead of file contents."""

    artifact_id: str
    sha256: str
    file_name: str
    media_type: str
    size_bytes: int
    storage_key: str
    provenance: str
    authorization_status: str
    created_at: str

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedArtifact:
    handle: ArtifactHandle
    path: Path


class LocalArtifactStore:
    """Store authorized user-selected CSVs under one local runtime root."""

    def __init__(self, root: Path, *, max_artifact_bytes: int = 100 * 1024 * 1024):
        if max_artifact_bytes < 1:
            raise ValueError("max_artifact_bytes must be positive")
        self.root = Path(root).expanduser().resolve()
        self.objects_dir = self.root / "objects"
        self.temp_dir = self.root / "tmp"
        self.database_path = self.root / "runtime.sqlite3"
        self.max_artifact_bytes = max_artifact_bytes
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Commit/rollback and close explicitly; Windows cannot delete open SQLite files."""
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize_database(self) -> None:
        try:
            with self._connection() as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS local_artifacts (
                        artifact_id TEXT PRIMARY KEY,
                        sha256 TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        media_type TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL CHECK(size_bytes > 0),
                        storage_key TEXT NOT NULL,
                        provenance TEXT NOT NULL,
                        authorization_status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        CHECK(length(sha256) = 64),
                        UNIQUE(storage_key, artifact_id)
                    )
                    """
                )
        except sqlite3.Error as error:
            logger.exception("local_artifact_database_init_failed error_type=%s", type(error).__name__)
            raise LocalArtifactError("LOCAL_STORE_UNAVAILABLE", "本机产物存储无法初始化。") from error

    @staticmethod
    def _safe_file_name(file_name: str) -> str:
        if not isinstance(file_name, str) or "\x00" in file_name:
            raise LocalArtifactError("ARTIFACT_FILE_NAME_INVALID", "文件名无效。")
        normalized = file_name.replace("\\", "/")
        name = PurePosixPath(normalized).name.strip()
        if not name or len(name) > 180 or Path(name).suffix.lower() != ".csv":
            raise LocalArtifactError("ARTIFACT_CSV_REQUIRED", "请选择 CSV 文件。")
        return name

    def import_csv(
        self,
        source: BinaryIO,
        *,
        file_name: str,
        authorization_confirmed: bool,
    ) -> ArtifactHandle:
        """Copy one explicitly authorized CSV into the local content store."""
        if not authorization_confirmed:
            raise LocalArtifactError(
                "ARTIFACT_AUTHORIZATION_REQUIRED",
                "导入前请确认你有权在本机处理此文件。",
            )
        safe_name = self._safe_file_name(file_name)
        temporary_path: Path | None = None
        digest = hashlib.sha256()
        byte_count = 0
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix="import-",
                suffix=".part",
                dir=self.temp_dir,
                delete=False,
            ) as destination:
                temporary_path = Path(destination.name)
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    if not isinstance(chunk, bytes):
                        raise LocalArtifactError("ARTIFACT_STREAM_INVALID", "无法读取所选文件。")
                    byte_count += len(chunk)
                    if byte_count > self.max_artifact_bytes:
                        raise LocalArtifactError("ARTIFACT_TOO_LARGE", "文件超过本机导入大小限制。")
                    digest.update(chunk)
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())

            if byte_count == 0:
                raise LocalArtifactError("ARTIFACT_EMPTY", "CSV 文件为空。")

            sha256 = digest.hexdigest()
            storage_key = f"objects/{sha256[:2]}/{sha256}.csv"
            object_path = (self.root / storage_key).resolve()
            if not object_path.is_relative_to(self.objects_dir.resolve()):
                raise LocalArtifactError("ARTIFACT_STORAGE_KEY_INVALID", "本机产物位置无效。")
            object_path.parent.mkdir(parents=True, exist_ok=True)
            if object_path.exists():
                temporary_path.unlink(missing_ok=True)
                temporary_path = None
            else:
                os.replace(temporary_path, object_path)
                temporary_path = None

            handle = ArtifactHandle(
                artifact_id=str(uuid4()),
                sha256=sha256,
                file_name=safe_name,
                media_type="text/csv",
                size_bytes=byte_count,
                storage_key=storage_key,
                provenance="user_selected_local_file",
                authorization_status="confirmed",
                created_at=datetime.now(UTC).isoformat(),
            )
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO local_artifacts (
                        artifact_id, sha256, file_name, media_type, size_bytes,
                        storage_key, provenance, authorization_status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        handle.artifact_id,
                        handle.sha256,
                        handle.file_name,
                        handle.media_type,
                        handle.size_bytes,
                        handle.storage_key,
                        handle.provenance,
                        handle.authorization_status,
                        handle.created_at,
                    ),
                )
            logger.info(
                "local_artifact_imported artifact_id=%s sha256=%s size_bytes=%s provenance=%s",
                handle.artifact_id,
                handle.sha256,
                handle.size_bytes,
                handle.provenance,
            )
            return handle
        except LocalArtifactError:
            raise
        except (OSError, sqlite3.Error) as error:
            logger.exception("local_artifact_import_failed error_type=%s", type(error).__name__)
            raise LocalArtifactError("LOCAL_ARTIFACT_IMPORT_FAILED", "本机文件导入失败。") from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def store_derived_csv(
        self,
        source: BinaryIO,
        *,
        file_name: str,
        source_artifact_id: str,
        producer_node_id: str,
        producer_run_id: str | None = None,
    ) -> ArtifactHandle:
        """Persist a CSV derived from a confirmed local artifact with traceable lineage."""
        if not isinstance(source_artifact_id, str) or not source_artifact_id.strip():
            raise LocalArtifactError("ARTIFACT_SOURCE_REQUIRED", "派生产物缺少来源 CSV。")
        source_handle = self.resolve(source_artifact_id.strip()).handle
        if source_handle.media_type != "text/csv":
            raise LocalArtifactError("ARTIFACT_CSV_REQUIRED", "派生 CSV 的来源必须是 CSV 产物。")
        if source_handle.authorization_status not in {"confirmed", "derived_from_confirmed_input"}:
            raise LocalArtifactError("ARTIFACT_AUTHORIZATION_REQUIRED", "来源 CSV 缺少有效授权记录。")

        safe_name = self._safe_file_name(file_name)
        if not isinstance(producer_node_id, str) or not producer_node_id.strip():
            raise LocalArtifactError("ARTIFACT_PRODUCER_INVALID", "派生 CSV 缺少来源节点。")
        if producer_run_id is not None and (
            not isinstance(producer_run_id, str) or not producer_run_id.strip()
        ):
            raise LocalArtifactError("ARTIFACT_RUN_INVALID", "派生 CSV 运行来源无效。")

        temporary_path: Path | None = None
        digest = hashlib.sha256()
        byte_count = 0
        try:
            # Stream to a temporary file so large outputs never accumulate in scheduler memory.
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix="derived-csv-",
                suffix=".part",
                dir=self.temp_dir,
                delete=False,
            ) as destination:
                temporary_path = Path(destination.name)
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    if not isinstance(chunk, bytes):
                        raise LocalArtifactError("ARTIFACT_STREAM_INVALID", "无法读取派生 CSV。")
                    byte_count += len(chunk)
                    if byte_count > self.max_artifact_bytes:
                        raise LocalArtifactError("ARTIFACT_TOO_LARGE", "派生 CSV 超过本机产物大小限制。")
                    digest.update(chunk)
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())

            if byte_count == 0:
                raise LocalArtifactError("ARTIFACT_EMPTY", "派生 CSV 为空。")

            sha256 = digest.hexdigest()
            storage_key = f"objects/{sha256[:2]}/{sha256}.csv"
            object_path = (self.root / storage_key).resolve()
            if not object_path.is_relative_to(self.objects_dir.resolve()):
                raise LocalArtifactError("ARTIFACT_STORAGE_KEY_INVALID", "本机产物位置无效。")
            object_path.parent.mkdir(parents=True, exist_ok=True)
            if object_path.exists():
                temporary_path.unlink(missing_ok=True)
                temporary_path = None
            else:
                os.replace(temporary_path, object_path)
                temporary_path = None

            parent_id = source_handle.artifact_id[:64]
            producer_id = producer_node_id.strip()[:128]
            provenance = (
                f"workflow_run:{producer_run_id.strip()[:64]}:node:{producer_id}:source:{parent_id}"
                if producer_run_id is not None
                else f"workflow_node:{producer_id}:source:{parent_id}"
            )
            handle = ArtifactHandle(
                artifact_id=str(uuid4()),
                sha256=sha256,
                file_name=safe_name,
                media_type="text/csv",
                size_bytes=byte_count,
                storage_key=storage_key,
                provenance=provenance,
                authorization_status="derived_from_confirmed_input",
                created_at=datetime.now(UTC).isoformat(),
            )
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO local_artifacts (
                        artifact_id, sha256, file_name, media_type, size_bytes,
                        storage_key, provenance, authorization_status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        handle.artifact_id,
                        handle.sha256,
                        handle.file_name,
                        handle.media_type,
                        handle.size_bytes,
                        handle.storage_key,
                        handle.provenance,
                        handle.authorization_status,
                        handle.created_at,
                    ),
                )
            logger.info(
                "local_derived_csv_stored artifact_id=%s source_artifact_id=%s sha256=%s size_bytes=%s producer_node_id=%s",
                handle.artifact_id,
                parent_id,
                handle.sha256,
                handle.size_bytes,
                producer_id,
            )
            return handle
        except LocalArtifactError:
            raise
        except (OSError, sqlite3.Error) as error:
            logger.exception(
                "local_derived_csv_store_failed source_artifact_id=%s error_type=%s",
                source_handle.artifact_id,
                type(error).__name__,
            )
            raise LocalArtifactError("LOCAL_ARTIFACT_WRITE_FAILED", "本机派生 CSV 写入失败。") from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def resolve(self, artifact_id: str | UUID) -> ResolvedArtifact:
        """Resolve only handles recorded by this local store and contained under its root."""
        try:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT * FROM local_artifacts WHERE artifact_id = ?",
                    (str(artifact_id),),
                ).fetchone()
        except sqlite3.Error as error:
            logger.exception("local_artifact_lookup_failed error_type=%s", type(error).__name__)
            raise LocalArtifactError("LOCAL_STORE_UNAVAILABLE", "本机产物索引读取失败。") from error
        if row is None:
            raise LocalArtifactError("ARTIFACT_NOT_FOUND", "本机产物不存在或已移除。")

        storage_key = row["storage_key"]
        if not isinstance(storage_key, str) or Path(storage_key).is_absolute():
            raise LocalArtifactError("ARTIFACT_STORAGE_KEY_INVALID", "本机产物索引无效。")
        path = (self.root / storage_key).resolve()
        if not path.is_relative_to(self.objects_dir.resolve()):
            raise LocalArtifactError("ARTIFACT_STORAGE_KEY_INVALID", "本机产物索引无效。")
        try:
            stat = path.stat()
        except OSError as error:
            logger.warning("local_artifact_file_missing artifact_id=%s", str(artifact_id))
            raise LocalArtifactError("ARTIFACT_FILE_MISSING", "本机产物文件不可用。") from error
        if stat.st_size != row["size_bytes"]:
            raise LocalArtifactError("ARTIFACT_SIZE_MISMATCH", "本机产物已变化，请重新导入。")

        handle = ArtifactHandle(
            artifact_id=row["artifact_id"],
            sha256=row["sha256"],
            file_name=row["file_name"],
            media_type=row["media_type"],
            size_bytes=row["size_bytes"],
            storage_key=row["storage_key"],
            provenance=row["provenance"],
            authorization_status=row["authorization_status"],
            created_at=row["created_at"],
        )
        return ResolvedArtifact(handle=handle, path=path)

    def read_csv_preflight_report(self, artifact_id: str | UUID) -> dict[str, object]:
        """Read only a registered, small CSV structure report; never expose arbitrary files."""
        resolved = self.resolve(artifact_id)
        if resolved.handle.media_type != "application/json":
            raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "此产物不是可查看的结构报告。")
        if resolved.handle.size_bytes > 2 * 1024 * 1024:
            raise LocalArtifactError("ARTIFACT_REPORT_TOO_LARGE", "结构报告超过页面查看上限。")
        try:
            content = resolved.path.read_bytes()
            if hashlib.sha256(content).hexdigest() != resolved.handle.sha256:
                raise LocalArtifactError("ARTIFACT_CONTENT_HASH_MISMATCH", "结构报告内容校验失败。")
            report = json.loads(content)
        except LocalArtifactError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            logger.exception("local_report_read_failed artifact_id=%s", str(artifact_id))
            raise LocalArtifactError("ARTIFACT_REPORT_UNREADABLE", "本机结构报告无法读取。") from error
        if (
            not isinstance(report, dict)
            or report.get("report_type") != "csv_manifest_structural_preflight"
            or report.get("research_result") is not False
        ):
            raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "此产物不是可查看的结构预检报告。")
        return report

    def read_csv_descriptive_summary_report(self, artifact_id: str | UUID) -> dict[str, object]:
        """Read a bounded, validated exploratory summary from the local artifact store."""
        resolved = self.resolve(artifact_id)
        if (
            resolved.handle.media_type != "application/json"
            or resolved.handle.file_name != "csv-descriptive-summary.json"
        ):
            raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "此产物不是可查看的描述统计报告。")
        if resolved.handle.authorization_status != "derived_from_confirmed_input":
            raise LocalArtifactError("ARTIFACT_AUTHORIZATION_REQUIRED", "此报告没有已授权输入来源。")
        if resolved.handle.size_bytes > 16 * 1024 * 1024:
            raise LocalArtifactError("ARTIFACT_REPORT_TOO_LARGE", "描述统计报告超过页面查看上限。")
        try:
            # Bound the read itself in case the underlying file changes after resolve() checks its size.
            with resolved.path.open("rb") as source:
                content = source.read(16 * 1024 * 1024 + 1)
            if len(content) > 16 * 1024 * 1024:
                raise LocalArtifactError("ARTIFACT_REPORT_TOO_LARGE", "描述统计报告超过页面查看上限。")
            if hashlib.sha256(content).hexdigest() != resolved.handle.sha256:
                raise LocalArtifactError("ARTIFACT_CONTENT_HASH_MISMATCH", "描述统计报告内容校验失败。")
            report = json.loads(content)
        except LocalArtifactError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            logger.exception("local_csv_descriptive_summary_read_failed artifact_id=%s", str(artifact_id))
            raise LocalArtifactError("ARTIFACT_REPORT_UNREADABLE", "本机描述统计报告无法读取。") from error

        def invalid_report() -> LocalArtifactError:
            return LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "此产物不是受支持的 CSV 描述统计报告。")

        def valid_count(value: object, *, maximum: int | None = None) -> bool:
            return (
                type(value) is int
                and value >= 0
                and (maximum is None or value <= maximum)
            )

        def valid_number(value: object) -> bool:
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return False
            try:
                return math.isfinite(value)
            except OverflowError:
                return False

        if (
            not isinstance(report, dict)
            or report.get("report_type") != "csv_descriptive_summary"
            or report.get("label") != "探索性描述统计摘要，非科研结论"
            or report.get("research_result") is not False
            or report.get("summary_method") != "ict.csv-descriptive-summary.v1"
            or not isinstance(report.get("missing_definition"), str)
            or not valid_count(report.get("row_count"))
            or not valid_count(report.get("column_count"), maximum=2_000)
            or not isinstance(report.get("columns"), list)
            or len(report["columns"]) != report.get("column_count")
        ):
            raise invalid_report()

        input_report = report.get("input")
        if not isinstance(input_report, dict):
            raise invalid_report()
        input_id = input_report.get("artifact_id")
        input_sha256 = input_report.get("sha256")
        input_size = input_report.get("size_bytes")
        input_provenance = input_report.get("provenance")
        input_authorization = input_report.get("authorization_status")
        if (
            not isinstance(input_id, str)
            or not 1 <= len(input_id) <= 64
            or not isinstance(input_sha256, str)
            or len(input_sha256) != 64
            or any(character not in "0123456789abcdef" for character in input_sha256.lower())
            or not valid_count(input_size)
            or not isinstance(input_provenance, str)
            or len(input_provenance) > 256
            or not isinstance(input_authorization, str)
            or input_authorization not in {"confirmed", "derived_from_confirmed_input"}
        ):
            raise invalid_report()

        row_count = report["row_count"]
        safe_columns: list[dict[str, object]] = []
        for column in report["columns"]:
            if not isinstance(column, dict):
                raise invalid_report()
            name = column.get("name")
            kind = column.get("kind")
            missing_count = column.get("missing_count")
            missing_rate = column.get("missing_rate")
            if (
                not isinstance(name, str)
                or not 1 <= len(name) <= 256
                or not isinstance(kind, str)
                or kind not in {"numeric", "categorical", "all_missing"}
                or type(column.get("row_count")) is not int
                or column.get("row_count") != row_count
                or not valid_count(missing_count, maximum=row_count)
                or not valid_number(missing_rate)
                or not 0 <= missing_rate <= 1
                or (row_count == 0 and missing_rate != 0)
                or (row_count > 0 and abs(missing_rate - missing_count / row_count) > 1e-9)
            ):
                raise invalid_report()

            numeric_summary = column.get("numeric_summary")
            category_summary = column.get("category_summary")
            safe_column: dict[str, object] = {
                "name": name,
                "kind": kind,
                "row_count": row_count,
                "missing_count": missing_count,
                "missing_rate": missing_rate,
                "numeric_summary": None,
                "category_summary": None,
            }
            if kind == "numeric":
                if (
                    missing_count == row_count
                    or not isinstance(numeric_summary, dict)
                    or category_summary is not None
                    or not all(valid_number(numeric_summary.get(field)) for field in ("minimum", "maximum", "mean"))
                    or numeric_summary["minimum"] > numeric_summary["maximum"]
                    or not numeric_summary["minimum"] <= numeric_summary["mean"] <= numeric_summary["maximum"]
                ):
                    raise invalid_report()
                safe_column["numeric_summary"] = {
                    field: numeric_summary[field] for field in ("minimum", "maximum", "mean")
                }
            elif kind == "categorical":
                if missing_count == row_count or numeric_summary is not None or not isinstance(category_summary, dict):
                    raise invalid_report()
                truncated = category_summary.get("truncated")
                distinct_count = category_summary.get("distinct_value_count")
                top_values = category_summary.get("top_values")
                if not isinstance(truncated, bool) or not isinstance(top_values, list) or len(top_values) > 10:
                    raise invalid_report()
                if truncated:
                    if distinct_count is not None or top_values:
                        raise invalid_report()
                elif not valid_count(distinct_count, maximum=500) or distinct_count < 1:
                    raise invalid_report()
                safe_top_values: list[dict[str, object]] = []
                seen_values: set[str] = set()
                for item in top_values:
                    if (
                        not isinstance(item, dict)
                        or not isinstance(item.get("value"), str)
                        or len(item["value"]) > 256
                        or not valid_count(item.get("count"), maximum=row_count - missing_count)
                        or item["count"] < 1
                        or item["value"] in seen_values
                    ):
                        raise invalid_report()
                    seen_values.add(item["value"])
                    safe_top_values.append({"value": item["value"], "count": item["count"]})
                if not truncated and len(seen_values) > distinct_count:
                    raise invalid_report()
                safe_column["category_summary"] = {
                    "distinct_value_count": distinct_count,
                    "top_values": safe_top_values,
                    "truncated": truncated,
                }
            else:
                if missing_count != row_count or numeric_summary is not None or category_summary is not None:
                    raise invalid_report()
            safe_columns.append(safe_column)

        return {
            "report_type": "csv_descriptive_summary",
            "label": "探索性描述统计摘要，非科研结论",
            "research_result": False,
            "summary_method": "ict.csv-descriptive-summary.v1",
            "missing_definition": report["missing_definition"][:500],
            "input": {
                "artifact_id": input_id,
                "sha256": input_sha256.lower(),
                "size_bytes": input_size,
                "provenance": input_provenance,
                "authorization_status": input_authorization,
            },
            "row_count": row_count,
            "column_count": report["column_count"],
            "columns": safe_columns,
            "limitations": [
                "本摘要仅描述当前 CSV 的字段、空白单元格和取值分布，不验证数据真实性、实验设计、抽样偏倚或因果关系。",
                "数值字段按有限浮点数解析；摘要不包含假设检验、置信区间或科研结论。",
                "类别频数最多追踪每列 500 个、全表 5,000 个不同值；类别值超过 256 字符或触及上限时，该列频数将省略。",
            ],
        }

    def read_csv_folder_quality_report(self, artifact_id: str | UUID) -> dict[str, object]:
        """Read a bounded, hash-verified, allowlisted CSV folder quality report."""
        resolved = self.resolve(artifact_id)
        if (
            resolved.handle.media_type != "application/json"
            or resolved.handle.file_name != "csv-folder-quality-report.json"
        ):
            raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "此产物不是可查看的 CSV 文件夹质量报告。")
        if resolved.handle.authorization_status != "derived_from_confirmed_input":
            raise LocalArtifactError("ARTIFACT_AUTHORIZATION_REQUIRED", "此报告没有已授权输入来源。")
        max_report_bytes = 16 * 1024 * 1024
        if resolved.handle.size_bytes > max_report_bytes:
            raise LocalArtifactError("ARTIFACT_REPORT_TOO_LARGE", "CSV 文件夹质量报告超过页面查看上限。")
        try:
            with resolved.path.open("rb") as source:
                content = source.read(max_report_bytes + 1)
            if len(content) > max_report_bytes:
                raise LocalArtifactError("ARTIFACT_REPORT_TOO_LARGE", "CSV 文件夹质量报告超过页面查看上限。")
            if hashlib.sha256(content).hexdigest() != resolved.handle.sha256:
                raise LocalArtifactError("ARTIFACT_CONTENT_HASH_MISMATCH", "CSV 文件夹质量报告校验失败。")
            report = json.loads(content)
        except LocalArtifactError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            logger.exception("local_csv_folder_quality_report_read_failed artifact_id=%s", str(artifact_id))
            raise LocalArtifactError("ARTIFACT_REPORT_UNREADABLE", "本机 CSV 文件夹质量报告无法读取。") from error

        if not isinstance(report, dict):
            raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "CSV 文件夹质量报告格式无效。")
        collection = report.get("collection")
        summary = report.get("summary")
        rules = report.get("rules")
        files = report.get("files")
        if (
            report.get("report_type") != "csv_folder_quality_v1"
            or report.get("label") != "本机 CSV 文件夹质量检查报告，非科研结果"
            or report.get("research_result") is not False
            or report.get("rules_version") != "ict.csv-folder-quality.v1"
            or not isinstance(collection, dict)
            or not isinstance(summary, dict)
            or not isinstance(rules, dict)
            or not isinstance(files, list)
            or not 1 <= len(files) <= 200
        ):
            raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "CSV 文件夹质量报告格式无效。")

        def valid_count(value: object, maximum: int | None = None) -> bool:
            return type(value) is int and value >= 0 and (maximum is None or value <= maximum)

        def valid_digest(value: object) -> bool:
            return (
                isinstance(value, str)
                and len(value) == 64
                and all(character in "0123456789abcdef" for character in value.lower())
            )

        if (
            not isinstance(collection.get("folder_name"), str)
            or len(collection["folder_name"]) > 120
            or not valid_digest(collection.get("collection_sha256"))
            or not valid_count(collection.get("file_count"), 200)
            or collection.get("file_count") != len(files)
            or not valid_count(collection.get("ignored_file_count"), 100_000)
            or not valid_count(collection.get("total_size_bytes"), 100 * 1024 * 1024)
            or summary.get("status") not in {"passed", "warning", "blocked"}
            or summary.get("file_count") != len(files)
            or not all(valid_count(summary.get(key), len(files)) for key in ("passed_count", "warning_count", "blocked_count"))
            or sum(summary[key] for key in ("passed_count", "warning_count", "blocked_count")) != len(files)
            or not isinstance(rules.get("required_columns"), list)
            or not isinstance(rules.get("unique_key_columns"), list)
            or not isinstance(rules.get("max_missing_rate"), (int, float))
            or isinstance(rules.get("max_missing_rate"), bool)
            or not 0 <= rules["max_missing_rate"] <= 1
        ):
            raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "CSV 文件夹质量报告摘要字段无效。")

        for item in files:
            if not isinstance(item, dict):
                raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "CSV 文件夹质量报告包含无效文件项。")
            relative_path = item.get("relative_path")
            columns = item.get("columns")
            missing_counts = item.get("missing_counts")
            issues = item.get("issues")
            if (
                not isinstance(relative_path, str)
                or len(relative_path) > 500
                or relative_path.startswith(("/", "\\"))
                or ".." in PurePosixPath(relative_path.replace("\\", "/")).parts
                or not relative_path.casefold().endswith(".csv")
                or not valid_digest(item.get("sha256"))
                or not valid_count(item.get("size_bytes"), self.max_artifact_bytes)
                or not valid_count(item.get("row_count"))
                or not valid_count(item.get("column_count"), 500)
                or item.get("status") not in {"passed", "warning", "blocked"}
                or not isinstance(columns, list)
                or len(columns) != item.get("column_count")
                or not isinstance(missing_counts, list)
                or len(missing_counts) != len(columns)
                or not valid_count(item.get("duplicate_key_count"))
                or not isinstance(issues, list)
                or len(issues) > 2_000
            ):
                raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "CSV 文件夹质量报告的文件项字段无效。")
            for column, missing in zip(columns, missing_counts, strict=True):
                if (
                    not isinstance(column, str)
                    or not 1 <= len(column) <= 256
                    or not isinstance(missing, dict)
                    or missing.get("field") != column
                    or not valid_count(missing.get("count"), item["row_count"])
                    or not isinstance(missing.get("rate"), (int, float))
                    or isinstance(missing.get("rate"), bool)
                    or not 0 <= missing["rate"] <= 1
                ):
                    raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "CSV 文件夹质量报告的字段统计无效。")
            for issue in issues:
                if (
                    not isinstance(issue, dict)
                    or not isinstance(issue.get("code"), str)
                    or len(issue["code"]) > 80
                    or issue.get("severity") not in {"warning", "blocker"}
                    or not valid_count(issue.get("count"))
                    or not isinstance(issue.get("fields"), list)
                    or len(issue["fields"]) > 100
                ):
                    raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "CSV 文件夹质量报告的问题项无效。")
        return report

    def read_crossref_metadata_report(self, artifact_id: str | UUID) -> dict[str, object]:
        """Read only the bounded, allowlisted public DOI metadata report."""
        resolved = self.resolve(artifact_id)
        if resolved.handle.media_type != "application/json":
            raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "此产物不是可查看的文献元数据。")
        if resolved.handle.authorization_status != "public_metadata":
            raise LocalArtifactError("ARTIFACT_AUTHORIZATION_REQUIRED", "此产物没有公开元数据授权标记。")
        if resolved.handle.size_bytes > 2 * 1024 * 1024:
            raise LocalArtifactError("ARTIFACT_REPORT_TOO_LARGE", "文献元数据超过页面查看上限。")
        try:
            content = resolved.path.read_bytes()
            if hashlib.sha256(content).hexdigest() != resolved.handle.sha256:
                raise LocalArtifactError("ARTIFACT_CONTENT_HASH_MISMATCH", "文献元数据校验失败。")
            report = json.loads(content)
        except LocalArtifactError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            logger.exception("local_crossref_report_read_failed artifact_id=%s", str(artifact_id))
            raise LocalArtifactError("ARTIFACT_REPORT_UNREADABLE", "本机文献元数据无法读取。") from error

        source_url = report.get("source_url") if isinstance(report, dict) else None
        try:
            source_parts = urlsplit(source_url) if isinstance(source_url, str) else None
            valid_source = bool(
                source_parts
                and source_parts.scheme == "https"
                and source_parts.hostname == "api.crossref.org"
                and source_parts.port is None
                and source_parts.path.startswith("/works/")
                and not source_parts.query
                and not source_parts.fragment
            )
        except ValueError:
            source_parts = None
            valid_source = False
        if (
            not isinstance(report, dict)
            or report.get("report_type") != "crossref_doi_metadata"
            or report.get("research_result") is not False
            or report.get("label") != "Crossref 公开文献元数据，非科研结果"
            or report.get("source_name") != "Crossref REST API"
            or not valid_source
            or not isinstance(report.get("doi"), str)
            or not isinstance(report.get("retrieved_at"), str)
            or not isinstance(report.get("authors"), list)
            or len(report["authors"]) > 100
        ):
            raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "此产物不是受支持的 Crossref 元数据报告。")

        # Reconstruct the response with a strict field allowlist before exposing it to the UI.
        allowed_text_fields = (
            "title", "container_title", "publisher", "published_date", "work_type", "landing_page",
        )
        safe_report: dict[str, object] = {
            "report_type": report["report_type"],
            "label": report["label"],
            "research_result": False,
            "source_name": report["source_name"],
            "source_url": report["source_url"],
            "retrieved_at": report["retrieved_at"][:100],
            "doi": report["doi"][:300],
            "verification_note": "元数据来自 Crossref 的登记记录，可能缺失或有误；请与出版方页面和论文原文核对。",
            "authors": [],
        }
        for field in allowed_text_fields:
            value = report.get(field)
            if value is not None and not isinstance(value, str):
                raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "Crossref 元数据字段格式无效。")
            if isinstance(value, str):
                safe_report[field] = value[:2000]
        safe_authors: list[dict[str, str]] = []
        for author in report["authors"]:
            if not isinstance(author, dict) or not isinstance(author.get("name"), str):
                raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "Crossref 作者字段格式无效。")
            safe_author = {"name": author["name"][:300]}
            if isinstance(author.get("orcid"), str):
                safe_author["orcid"] = author["orcid"][:100]
            safe_authors.append(safe_author)
        safe_report["authors"] = safe_authors
        assert source_parts is not None  # valid_source above guarantees a parsed fixed-host URL.
        request_doi = unquote(source_parts.path.removeprefix("/works/"))
        if request_doi.casefold() != report["doi"].casefold():
            raise LocalArtifactError("ARTIFACT_REPORT_TYPE_UNSUPPORTED", "Crossref 来源与 DOI 不匹配。")
        return safe_report

    def store_json_report(
        self,
        report: dict[str, object],
        *,
        producer_node_id: str,
        producer_run_id: str | None = None,
        file_name: str = "quality-report.json",
        authorization_status: str = "derived_from_confirmed_input",
    ) -> ArtifactHandle:
        """Persist a small aggregate report without writing CSV row contents to metadata."""
        try:
            content = json.dumps(
                report,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise LocalArtifactError("REPORT_NOT_SERIALIZABLE", "结构报告无法安全保存。") from error
        if not content:
            raise LocalArtifactError("REPORT_EMPTY", "结构报告为空。")
        if len(content) > self.max_artifact_bytes:
            raise LocalArtifactError("REPORT_TOO_LARGE", "结构报告超过本机保存限制。")
        if not isinstance(producer_node_id, str) or not producer_node_id.strip():
            raise LocalArtifactError("REPORT_PRODUCER_INVALID", "结构报告缺少来源节点。")
        if producer_run_id is not None and (
            not isinstance(producer_run_id, str) or not producer_run_id.strip()
        ):
            raise LocalArtifactError("REPORT_RUN_INVALID", "结构报告运行来源无效。")
        if file_name not in {
            "quality-report.json",
            "crossref-doi-metadata.json",
            "csv-descriptive-summary.json",
            "csv-folder-quality-report.json",
        }:
            raise LocalArtifactError("REPORT_FILE_NAME_INVALID", "结构报告文件名不在允许范围内。")
        if authorization_status not in {"derived_from_confirmed_input", "public_metadata"}:
            raise LocalArtifactError("REPORT_AUTHORIZATION_INVALID", "结构报告授权状态无效。")

        digest = hashlib.sha256(content).hexdigest()
        storage_key = f"objects/{digest[:2]}/{digest}.json"
        object_path = (self.root / storage_key).resolve()
        if not object_path.is_relative_to(self.objects_dir.resolve()):
            raise LocalArtifactError("ARTIFACT_STORAGE_KEY_INVALID", "本机产物位置无效。")
        object_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix="report-",
                suffix=".part",
                dir=self.temp_dir,
                delete=False,
            ) as destination:
                temporary_path = Path(destination.name)
                destination.write(content)
                destination.flush()
                os.fsync(destination.fileno())
            if object_path.exists():
                temporary_path.unlink(missing_ok=True)
                temporary_path = None
            else:
                os.replace(temporary_path, object_path)
                temporary_path = None

            handle = ArtifactHandle(
                artifact_id=str(uuid4()),
                sha256=digest,
                file_name=file_name,
                media_type="application/json",
                size_bytes=len(content),
                storage_key=storage_key,
                provenance=(
                    f"workflow_run:{producer_run_id.strip()[:64]}:node:{producer_node_id.strip()[:128]}"
                    if producer_run_id is not None
                    else f"workflow_node:{producer_node_id.strip()[:128]}"
                ),
                authorization_status=authorization_status,
                created_at=datetime.now(UTC).isoformat(),
            )
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO local_artifacts (
                        artifact_id, sha256, file_name, media_type, size_bytes,
                        storage_key, provenance, authorization_status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        handle.artifact_id,
                        handle.sha256,
                        handle.file_name,
                        handle.media_type,
                        handle.size_bytes,
                        handle.storage_key,
                        handle.provenance,
                        handle.authorization_status,
                        handle.created_at,
                    ),
                )
            logger.info(
                "local_report_artifact_stored artifact_id=%s sha256=%s size_bytes=%s producer_node_id=%s",
                handle.artifact_id,
                handle.sha256,
                handle.size_bytes,
                producer_node_id.strip()[:128],
            )
            return handle
        except sqlite3.Error as error:
            logger.exception("local_report_artifact_index_failed error_type=%s", type(error).__name__)
            raise LocalArtifactError("LOCAL_STORE_UNAVAILABLE", "本机产物索引写入失败。") from error
        except OSError as error:
            logger.exception("local_report_artifact_write_failed error_type=%s", type(error).__name__)
            raise LocalArtifactError("LOCAL_ARTIFACT_WRITE_FAILED", "本机结构报告写入失败。") from error
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
