"""Local-only checks for a generic machine-learning CSV manifest."""

from __future__ import annotations

# Expose the bundled component contract version for workflow-runtime admission checks.
ICT_COMPONENT_DEPENDENCY_VERSION = "1.0.0"

import csv
import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


REQUIRED_COLUMNS = ("record_id", "group_id", "split", "label")


class ManifestQualityError(ValueError):
    """Safe validation error that never includes source paths or row contents."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        severity: Literal["blocker", "error"] = "error",
        guidance: str = "",
    ) -> None:
        self.code = code
        self.severity = severity
        self.guidance = guidance
        super().__init__(message)


@dataclass(frozen=True)
class ManifestIssue:
    code: str
    message: str
    count: int
    line_numbers: tuple[int, ...]
    field: str | None = None
    severity: Literal["blocker", "warning"] = "blocker"
    guidance: str = ""


@dataclass(frozen=True)
class ManifestQualityReport:
    row_count: int
    columns: tuple[str, ...]
    sha256: str
    split_counts: tuple[tuple[str, int], ...]
    label_category_count: int
    issues: tuple[ManifestIssue, ...]

    @property
    def has_blockers(self) -> bool:
        """Blockers prevent this generic structural check from passing."""
        return any(issue.severity == "blocker" for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        """Warnings identify content outside the checks performed here."""
        return any(issue.severity == "warning" for issue in self.issues)

    @property
    def status(self) -> Literal["blocker", "warning", "success"]:
        """Summarize local structural preflight without implying research approval."""
        if self.has_blockers:
            return "blocker"
        if self.has_warnings:
            return "warning"
        return "success"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ManifestQualityError("manifest_unreadable", "无法读取清单文件，请检查文件和访问权限。") from exc
    return digest.hexdigest()


def inspect_manifest(path: str | Path) -> ManifestQualityReport:
    """Inspect a UTF-8 CSV locally and return counts without retaining record values."""
    manifest_path = Path(path)
    try:
        file_state_before = manifest_path.stat()
    except OSError as exc:
        raise ManifestQualityError("manifest_unreadable", "无法读取清单文件，请检查文件和访问权限。") from exc
    source_hash = _file_sha256(manifest_path)

    split_counts: Counter[str] = Counter()
    label_categories: set[str] = set()
    record_lines: dict[str, list[int]] = defaultdict(list)
    group_splits: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    empty_field_lines: dict[str, list[int]] = {column: [] for column in REQUIRED_COLUMNS}
    malformed_width_lines: list[int] = []
    row_count = 0
    headers: tuple[str, ...] = ()

    try:
        with manifest_path.open("r", encoding="utf-8-sig", newline="") as source:
            # Match server parsing so malformed quoting becomes a blocker locally too.
            reader = csv.DictReader(source, strict=True)
            raw_headers = reader.fieldnames
            if not raw_headers:
                raise ManifestQualityError(
                    "manifest_header_missing",
                    "CSV 清单缺少表头。",
                    severity="blocker",
                    guidance="在第一行添加 CSV 表头，并包含所有必需列。",
                )

            normalized_headers = tuple(header.strip() if header else "" for header in raw_headers)
            if len(set(normalized_headers)) != len(normalized_headers):
                raise ManifestQualityError(
                    "manifest_header_duplicate",
                    "CSV 清单存在重复或空白列名。",
                    severity="blocker",
                    guidance="整理首行列名，确保每个列名非空且唯一。",
                )
            missing_columns = [column for column in REQUIRED_COLUMNS if column not in normalized_headers]
            if missing_columns:
                missing_text = "、".join(missing_columns)
                raise ManifestQualityError(
                    "missing_required_columns",
                    f"清单缺少必需列：{missing_text}。",
                    severity="blocker",
                    guidance=f"按通用清单格式补上缺少的必需列（{missing_text}），再重新检查。",
                )

            headers = normalized_headers
            # DictReader uses fieldnames for row dictionaries, so trimmed headers stay consistent.
            reader.fieldnames = list(normalized_headers)

            for row in reader:
                row_count += 1
                line_number = reader.line_num
                if None in row or any(value is None for value in row.values()):
                    malformed_width_lines.append(line_number)

                values: dict[str, str] = {}
                for column in REQUIRED_COLUMNS:
                    raw_value = row.get(column)
                    value = raw_value.strip() if isinstance(raw_value, str) else ""
                    values[column] = value
                    if not value:
                        empty_field_lines[column].append(line_number)

                record_id = values["record_id"]
                group_id = values["group_id"]
                split = values["split"]
                label = values["label"]
                if record_id:
                    record_lines[record_id].append(line_number)
                if group_id and split:
                    group_splits[group_id][split].append(line_number)
                if split:
                    split_counts[split] += 1
                if label:
                    label_categories.add(label)
    except ManifestQualityError:
        raise
    except UnicodeDecodeError as exc:
        raise ManifestQualityError(
            "invalid_encoding",
            "清单编码无法识别，请另存为 UTF-8 CSV 后重试。",
            severity="blocker",
            guidance="将清单另存为 UTF-8 CSV 后重新检查。",
        ) from exc
    except csv.Error as exc:
        raise ManifestQualityError(
            "invalid_csv",
            "CSV 清单格式无法解析，请检查分隔符和引号。",
            severity="blocker",
            guidance="检查 CSV 分隔符和引号是否成对，修正后重新检查。",
        ) from exc
    except OSError as exc:
        raise ManifestQualityError("manifest_unreadable", "无法读取清单文件，请检查文件和访问权限。") from exc

    issues: list[ManifestIssue] = []
    extra_columns = tuple(column for column in headers if column not in REQUIRED_COLUMNS)
    if extra_columns:
        issues.append(
            ManifestIssue(
                code="unvalidated_extra_columns",
                message="存在未纳入本机通用预检的额外列。",
                count=len(extra_columns),
                line_numbers=(),
                severity="warning",
                guidance="确认额外列的含义与授权范围；当前通用预检不会验证这些列。",
            )
        )

    if row_count == 0:
        issues.append(
            ManifestIssue(
                code="no_records",
                message="清单没有数据行。",
                count=0,
                line_numbers=(),
                guidance="补充有效数据行后重新检查。",
            )
        )

    for field, lines in empty_field_lines.items():
        if lines:
            issues.append(
                ManifestIssue(
                    code="empty_required_value",
                    message=f"必需字段存在空值：{field}。",
                    count=len(lines),
                    line_numbers=tuple(lines),
                    field=field,
                    guidance="依据已确认的字段定义补齐必需值，再重新检查。",
                )
            )

    if malformed_width_lines:
        issues.append(
            ManifestIssue(
                code="row_width",
                message="部分记录的列数与表头不一致。",
                count=len(malformed_width_lines),
                line_numbers=tuple(malformed_width_lines),
                guidance="检查 CSV 分隔符、引号和每行列数，使记录列数与表头一致。",
            )
        )

    duplicate_lines: list[int] = []
    duplicate_record_count = 0
    for lines in record_lines.values():
        if len(lines) > 1:
            duplicate_lines.extend(lines)
            duplicate_record_count += len(lines) - 1
    if duplicate_lines:
        issues.append(
            ManifestIssue(
                code="duplicate_record_id",
                message="发现重复样本编号。",
                count=duplicate_record_count,
                line_numbers=tuple(sorted(set(duplicate_lines))),
                guidance="为每条记录指定唯一 record_id，并检查重复是否来自重复导入。",
            )
        )

    overlap_lines: list[int] = []
    overlap_group_count = 0
    for splits_by_group in group_splits.values():
        if len(splits_by_group) > 1:
            overlap_group_count += 1
            for lines in splits_by_group.values():
                overlap_lines.extend(lines)
    if overlap_lines:
        issues.append(
            ManifestIssue(
                code="group_split_overlap",
                message="发现同一分组跨拆分出现。",
                count=overlap_group_count,
                line_numbers=tuple(sorted(set(overlap_lines))),
                guidance="按 group_id 统一划分 split，确保同一分组只出现在一个拆分中。",
            )
        )

    try:
        file_state_after = manifest_path.stat()
    except OSError as exc:
        raise ManifestQualityError("manifest_unreadable", "无法读取清单文件，请检查文件和访问权限。") from exc
    if (
        file_state_before.st_size != file_state_after.st_size
        or file_state_before.st_mtime_ns != file_state_after.st_mtime_ns
    ):
        raise ManifestQualityError("manifest_changed", "检查过程中清单文件发生变化，请重新选择后重试。")

    return ManifestQualityReport(
        row_count=row_count,
        columns=headers,
        sha256=source_hash,
        split_counts=tuple(sorted(split_counts.items())),
        label_category_count=len(label_categories),
        issues=tuple(issues),
    )
