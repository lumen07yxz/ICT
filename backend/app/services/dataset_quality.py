"""Fail-closed generic manifest checks for the registered synthetic demo dataset."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from app.errors import AppError


logger = logging.getLogger("ict.quality")
REQUIRED_COLUMNS = ("record_id", "group_id", "split", "label")
DEMO_DATASET_VERSION = "dataset-synthetic-v1"
DEMO_MANIFEST_REF = "synthetic://demo-research/dataset-synthetic-v1/manifest"
RULE_SET_VERSION = "generic-manifest-v1"
DEMO_MANIFEST_PATH = Path(__file__).resolve().parents[1] / "data" / "demo_manifest.csv"
Severity = Literal["blocker", "warning"]


@dataclass(frozen=True)
class QualityIssue:
    code: str
    severity: Severity
    message: str
    count: int
    line_numbers: tuple[int, ...]
    guidance: str


@dataclass(frozen=True)
class DatasetQualityReport:
    dataset_version: str
    rule_set_version: str
    manifest_sha256: str
    row_count: int
    split_counts: tuple[tuple[str, int], ...]
    label_category_count: int
    issues: tuple[QualityIssue, ...]
    synthetic_only: bool
    research_ready: bool
    checked_at: datetime

    @property
    def status(self) -> Literal["blocker", "warning", "success"]:
        """Derive one clear state while keeping warnings distinct from blockers."""
        if any(issue.severity == "blocker" for issue in self.issues):
            return "blocker"
        if any(issue.severity == "warning" for issue in self.issues):
            return "warning"
        return "success"


def _report(
    raw_bytes: bytes,
    issues: list[QualityIssue],
    *,
    dataset_version: str = DEMO_DATASET_VERSION,
    row_count: int = 0,
    split_counts: Counter[str] | None = None,
    label_category_count: int = 0,
) -> DatasetQualityReport:
    """Create an aggregate-only report; row values and source paths never leave this function."""
    return DatasetQualityReport(
        dataset_version=dataset_version,
        rule_set_version=RULE_SET_VERSION,
        manifest_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        row_count=row_count,
        split_counts=tuple(sorted((split_counts or Counter()).items())),
        label_category_count=label_category_count,
        issues=tuple(issues),
        synthetic_only=True,
        research_ready=False,
        checked_at=datetime.now(timezone.utc),
    )


def inspect_manifest_bytes(raw_bytes: bytes, *, dataset_version: str = DEMO_DATASET_VERSION) -> DatasetQualityReport:
    """Check CSV structure without retaining or returning record, group, or label values."""
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return _report(
            raw_bytes,
            [
                QualityIssue(
                    code="invalid_encoding",
                    severity="blocker",
                    message="清单编码不是 UTF-8。",
                    count=1,
                    line_numbers=(),
                    guidance="将清单另存为 UTF-8 CSV 后重新检查。",
                )
            ],
            dataset_version=dataset_version,
        )

    try:
        # Strict parsing prevents malformed quoting from silently hiding later rows.
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        raw_headers = reader.fieldnames
        if not raw_headers:
            return _report(
                raw_bytes,
                [
                    QualityIssue(
                        code="manifest_header_missing",
                        severity="blocker",
                        message="CSV 清单缺少表头。",
                        count=1,
                        line_numbers=(),
                        guidance="在第一行添加包含必需列的 CSV 表头。",
                    )
                ],
                dataset_version=dataset_version,
            )

        headers = tuple(header.strip() if header else "" for header in raw_headers)
        if len(set(headers)) != len(headers):
            issue = QualityIssue(
                code="manifest_header_duplicate",
                severity="blocker",
                message="CSV 清单存在重复或空白列名。",
                count=1,
                line_numbers=(),
                guidance="整理首行列名，确保每个列名非空且唯一。",
            )
            return _report(raw_bytes, [issue], dataset_version=dataset_version)

        missing_columns = [column for column in REQUIRED_COLUMNS if column not in headers]
        if missing_columns:
            missing_text = "、".join(missing_columns)
            issue = QualityIssue(
                code="missing_required_columns",
                severity="blocker",
                message=f"清单缺少必需列：{missing_text}。",
                count=len(missing_columns),
                line_numbers=(),
                guidance=f"按通用清单格式补上缺少的必需列（{missing_text}），再重新检查。",
            )
            return _report(raw_bytes, [issue], dataset_version=dataset_version)

        # DictReader must use the same normalized names checked above.
        reader.fieldnames = list(headers)
        row_count = 0
        split_counts: Counter[str] = Counter()
        labels: set[str] = set()
        record_lines: dict[str, list[int]] = defaultdict(list)
        group_splits: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
        empty_lines: dict[str, list[int]] = {column: [] for column in REQUIRED_COLUMNS}
        malformed_lines: list[int] = []

        for row in reader:
            row_count += 1
            line_number = reader.line_num
            if None in row or any(value is None for value in row.values()):
                malformed_lines.append(line_number)
            values: dict[str, str] = {}
            for column in REQUIRED_COLUMNS:
                raw_value = row.get(column)
                value = raw_value.strip() if isinstance(raw_value, str) else ""
                values[column] = value
                if not value:
                    empty_lines[column].append(line_number)
            if values["record_id"]:
                record_lines[values["record_id"]].append(line_number)
            if values["group_id"] and values["split"]:
                group_splits[values["group_id"]][values["split"]].append(line_number)
            if values["split"]:
                split_counts[values["split"]] += 1
            if values["label"]:
                labels.add(values["label"])
    except csv.Error:
        issue = QualityIssue(
            code="invalid_csv",
            severity="blocker",
            message="CSV 清单格式无法解析。",
            count=1,
            line_numbers=(),
            guidance="检查 CSV 分隔符和引号，再重新检查。",
        )
        return _report(raw_bytes, [issue], dataset_version=dataset_version)

    issues: list[QualityIssue] = []
    extra_columns = tuple(column for column in headers if column not in REQUIRED_COLUMNS)
    if extra_columns:
        issues.append(
            QualityIssue(
                code="unvalidated_extra_columns",
                severity="warning",
                message="存在未纳入通用预检的额外列。",
                count=len(extra_columns),
                line_numbers=(),
                guidance="确认额外列的含义和授权范围；当前规则不会验证这些列。",
            )
        )
    if row_count == 0:
        issues.append(
            QualityIssue(
                code="no_records",
                severity="blocker",
                message="清单没有数据行。",
                count=0,
                line_numbers=(),
                guidance="补充有效数据行后重新检查。",
            )
        )
    for field, lines in empty_lines.items():
        if lines:
            issues.append(
                QualityIssue(
                    code="empty_required_value",
                    severity="blocker",
                    message=f"必需字段存在空值：{field}。",
                    count=len(lines),
                    line_numbers=tuple(lines),
                    guidance="依据已确认的字段定义补齐必需值，再重新检查。",
                )
            )
    if malformed_lines:
        issues.append(
            QualityIssue(
                code="row_width",
                severity="blocker",
                message="部分记录的列数与表头不一致。",
                count=len(malformed_lines),
                line_numbers=tuple(malformed_lines),
                guidance="检查 CSV 分隔符、引号和每行列数，使记录列数与表头一致。",
            )
        )

    duplicate_lines: list[int] = []
    duplicate_count = 0
    for lines in record_lines.values():
        if len(lines) > 1:
            duplicate_lines.extend(lines)
            duplicate_count += len(lines) - 1
    if duplicate_lines:
        issues.append(
            QualityIssue(
                code="duplicate_record_id",
                severity="blocker",
                message="发现重复样本编号。",
                count=duplicate_count,
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
            QualityIssue(
                code="group_split_overlap",
                severity="blocker",
                message="发现同一分组跨拆分出现。",
                count=overlap_group_count,
                line_numbers=tuple(sorted(set(overlap_lines))),
                guidance="按 group_id 统一划分 split，确保同一分组只出现在一个拆分中。",
            )
        )

    return _report(
        raw_bytes,
        issues,
        dataset_version=dataset_version,
        row_count=row_count,
        split_counts=split_counts,
        label_category_count=len(labels),
    )


def inspect_dataset_manifest(dataset: object) -> DatasetQualityReport:
    """Resolve only the immutable allow-listed synthetic fixture; never read client paths."""
    if (
        getattr(dataset, "version", None) != DEMO_DATASET_VERSION
        or getattr(dataset, "source", None) != "synthetic"
        or getattr(dataset, "manifest_ref", None) != DEMO_MANIFEST_REF
    ):
        raise AppError(409, "QUALITY_SOURCE_NOT_SUPPORTED")
    try:
        raw_bytes = DEMO_MANIFEST_PATH.read_bytes()
    except OSError as exc:
        logger.error(
            "dataset_quality_source_unavailable dataset_version=%s error_type=%s",
            DEMO_DATASET_VERSION,
            type(exc).__name__,
        )
        raise AppError(503, "QUALITY_SOURCE_UNAVAILABLE") from exc
    return inspect_manifest_bytes(raw_bytes, dataset_version=DEMO_DATASET_VERSION)
