"""Regression coverage for normalized CSV headers across local workflow nodes."""

import asyncio
import csv
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class LocalCsvHeaderNormalizationTests(unittest.TestCase):
    def test_column_selection_uses_trimmed_headers_and_preserves_data_values(self) -> None:
        from app.services.local_artifacts import LocalArtifactStore
        from app.services.local_csv_executor import (
            run_local_csv_column_selection,
            run_local_csv_preflight,
        )
        from app.services.workflow_scheduler import WorkflowNodeFailure

        content = b"\xef\xbb\xbfrecord_id, group_id ,split, label\nr1,g1,train,case-a\n"
        with tempfile.TemporaryDirectory() as directory:
            store = LocalArtifactStore(Path(directory))
            source = store.import_csv(
                BytesIO(content),
                file_name="manifest.csv",
                authorization_confirmed=True,
            )
            preflight = asyncio.run(
                run_local_csv_preflight(
                    {"id": "preflight", "parameters": {"artifact_id": source.artifact_id}},
                    {},
                    store,
                )
            )
            report = store.read_csv_preflight_report(preflight["quality_report"]["artifact_id"])
            self.assertEqual(report["columns"], ["record_id", "group_id", "split", "label"])

            try:
                selected = asyncio.run(
                    run_local_csv_column_selection(
                        {
                            "id": "select",
                            "parameters": {
                                "artifact_id": source.artifact_id,
                                "columns": "record_id,group_id,split,label",
                            },
                        },
                        {},
                        store,
                    )
                )
            except WorkflowNodeFailure as error:
                self.fail(f"expected trimmed headers to be selectable, got {error.code}")

            selected_path = store.resolve(selected["selected_csv"]["artifact_id"]).path
            with selected_path.open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(rows, [
                ["record_id", "group_id", "split", "label"],
                ["r1", "g1", "train", "case-a"],
            ])

    def test_descriptive_summary_reports_trimmed_header_names(self) -> None:
        from app.services.local_artifacts import LocalArtifactStore
        from app.services.local_csv_executor import run_local_csv_descriptive_summary

        content = b"record_id, group_id ,split, label\nr1,g1,train,case-a\n"
        with tempfile.TemporaryDirectory() as directory:
            store = LocalArtifactStore(Path(directory))
            source = store.import_csv(
                BytesIO(content),
                file_name="manifest.csv",
                authorization_confirmed=True,
            )
            result = asyncio.run(
                run_local_csv_descriptive_summary(
                    {"id": "summary", "parameters": {"artifact_id": source.artifact_id}},
                    {},
                    store,
                )
            )
            report = store.read_csv_descriptive_summary_report(
                result["summary_report"]["artifact_id"]
            )
            self.assertEqual(
                [column["name"] for column in report["columns"]],
                ["record_id", "group_id", "split", "label"],
            )

    def test_nodes_reject_headers_that_duplicate_after_trimming(self) -> None:
        from app.services.local_artifacts import LocalArtifactStore
        from app.services.local_csv_executor import (
            run_local_csv_column_selection,
            run_local_csv_descriptive_summary,
        )
        from app.services.workflow_scheduler import WorkflowNodeFailure

        content = b"record_id,group_id, group_id,label\nr1,g1,g2,case-a\n"
        with tempfile.TemporaryDirectory() as directory:
            store = LocalArtifactStore(Path(directory))
            source = store.import_csv(
                BytesIO(content),
                file_name="duplicate-headers.csv",
                authorization_confirmed=True,
            )
            nodes = (
                (
                    "select",
                    run_local_csv_column_selection,
                    {"artifact_id": source.artifact_id, "columns": "record_id,group_id,label"},
                ),
                (
                    "summary",
                    run_local_csv_descriptive_summary,
                    {"artifact_id": source.artifact_id},
                ),
            )
            for node_id, runner, parameters in nodes:
                with self.subTest(node=node_id):
                    try:
                        asyncio.run(
                            runner(
                                {"id": node_id, "parameters": parameters},
                                {},
                                store,
                            )
                        )
                    except WorkflowNodeFailure as error:
                        self.assertEqual(error.code, "CSV_HEADER_DUPLICATE")
                    else:
                        self.fail("expected headers that collide after trimming to be rejected")


if __name__ == "__main__":
    unittest.main()
