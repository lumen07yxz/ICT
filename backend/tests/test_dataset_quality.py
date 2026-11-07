"""Generic quality checks run only against explicitly registered synthetic manifests."""

from pathlib import Path
from types import SimpleNamespace
import importlib
import importlib.util
import sys
import unittest


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class DatasetQualityTests(unittest.TestCase):
    def quality_module(self):
        try:
            spec = importlib.util.find_spec("app.services.dataset_quality")
        except ModuleNotFoundError:
            spec = None
        self.assertIsNotNone(spec, "Server-side dataset quality checking is not implemented yet")
        return importlib.import_module("app.services.dataset_quality")

    def test_registered_synthetic_manifest_has_a_versioned_safe_report(self):
        quality = self.quality_module()
        dataset = SimpleNamespace(
            version="dataset-synthetic-v1",
            source="synthetic",
            manifest_ref="synthetic://demo-research/dataset-synthetic-v1/manifest",
        )

        report = quality.inspect_dataset_manifest(dataset)

        self.assertEqual(report.status, "success")
        self.assertEqual(report.rule_set_version, "generic-manifest-v1")
        self.assertGreater(report.row_count, 0)
        self.assertTrue(report.manifest_sha256)
        self.assertTrue(report.synthetic_only)
        self.assertFalse(report.research_ready)
        self.assertNotIn("demo-record", repr(report))

    def test_duplicate_ids_and_group_split_leakage_are_blockers_without_values(self):
        quality = self.quality_module()
        report = quality.inspect_manifest_bytes(
            b"record_id,group_id,split,label\n"
            b"hidden-record,hidden-group,train,hidden-label\n"
            b"hidden-record,hidden-group,test,hidden-label\n"
        )

        self.assertEqual(report.status, "blocker")
        self.assertEqual(
            {issue.code for issue in report.issues},
            {"duplicate_record_id", "group_split_overlap"},
        )
        self.assertTrue(all(issue.guidance for issue in report.issues))
        report_text = repr(report.issues)
        self.assertNotIn("hidden-record", report_text)
        self.assertNotIn("hidden-group", report_text)
        self.assertNotIn("hidden-label", report_text)

    def test_unterminated_quoted_field_is_a_blocker_without_values(self):
        quality = self.quality_module()
        report = quality.inspect_manifest_bytes(
            b"record_id,group_id,split,label\n"
            b'private-record,g-1,train,"private-label\n'
        )

        self.assertEqual(report.status, "blocker")
        self.assertEqual([issue.code for issue in report.issues], ["invalid_csv"])
        report_text = repr(report.issues)
        self.assertNotIn("private-record", report_text)
        self.assertNotIn("private-label", report_text)

    def test_valid_quoted_multiline_field_remains_a_single_record(self):
        quality = self.quality_module()
        report = quality.inspect_manifest_bytes(
            b"record_id,group_id,split,label\n"
            b'r-1,g-1,train,"alpha,\nbeta"\n'
        )

        self.assertEqual(report.status, "success")
        self.assertEqual(report.row_count, 1)
        self.assertEqual(report.label_category_count, 1)

    def test_unvalidated_extra_columns_are_warnings_and_not_blockers(self):
        quality = self.quality_module()
        report = quality.inspect_manifest_bytes(
            b"record_id,group_id,split,label,private-header\n"
            b"r-1,g-1,train,a,private-value\n"
        )

        self.assertEqual(report.status, "warning")
        self.assertEqual(report.issues[0].code, "unvalidated_extra_columns")
        self.assertNotIn("private-header", repr(report.issues))
        self.assertNotIn("private-value", repr(report.issues))

    def test_unregistered_manifest_references_fail_closed(self):
        quality = self.quality_module()
        dataset = SimpleNamespace(
            version="untrusted-version",
            source="external",
            manifest_ref="file:///etc/passwd",
        )

        with self.assertRaises(quality.AppError) as raised:
            quality.inspect_dataset_manifest(dataset)

        self.assertEqual(raised.exception.code, "QUALITY_SOURCE_NOT_SUPPORTED")


if __name__ == "__main__":
    unittest.main()
