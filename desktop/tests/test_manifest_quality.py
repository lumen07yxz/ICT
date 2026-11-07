import hashlib
import importlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


DESKTOP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DESKTOP_ROOT))


class ManifestQualityTests(unittest.TestCase):
    def quality_module(self):
        try:
            spec = importlib.util.find_spec("ict_desktop.manifest_quality")
        except ModuleNotFoundError:
            spec = None
        self.assertIsNotNone(spec, "Local CSV manifest validation must be implemented")
        return importlib.import_module("ict_desktop.manifest_quality")

    def write_manifest(self, directory, content):
        path = Path(directory) / "manifest.csv"
        path.write_text(content, encoding="utf-8", newline="")
        return path

    def test_valid_manifest_reports_counts_and_source_hash(self):
        quality = self.quality_module()
        content = (
            "record_id,group_id,split,label\n"
            "r-1,g-1,train,alpha\n"
            "r-2,g-2,train,beta\n"
            "r-3,g-3,validation,beta\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_manifest(directory, content)

            report = quality.inspect_manifest(path)
            unchanged_source = path.read_text(encoding="utf-8")

        self.assertEqual(report.row_count, 3)
        self.assertEqual(dict(report.split_counts), {"train": 2, "validation": 1})
        self.assertEqual(report.label_category_count, 2)
        self.assertEqual(report.sha256, hashlib.sha256(content.encode("utf-8")).hexdigest())
        self.assertEqual(report.issues, ())
        self.assertEqual(unchanged_source, content)

    def test_report_classifies_blocker_warning_and_success_with_safe_guidance(self):
        quality = self.quality_module()
        with tempfile.TemporaryDirectory() as directory:
            blocker_path = Path(directory) / "blocker.csv"
            blocker_path.write_text(
                "record_id,group_id,split,label\n"
                "r-1,g-1,train,alpha\n"
                "r-1,g-1,test,alpha\n",
                encoding="utf-8",
                newline="",
            )
            warning_path = Path(directory) / "warning.csv"
            warning_path.write_text(
                "record_id,group_id,split,label,private-extra-header\n"
                "r-1,g-1,train,alpha,private-extra-value\n",
                encoding="utf-8",
                newline="",
            )
            success_path = Path(directory) / "success.csv"
            success_path.write_text(
                "record_id,group_id,split,label\n"
                "r-1,g-1,train,alpha\n",
                encoding="utf-8",
                newline="",
            )

            blocker_report = quality.inspect_manifest(blocker_path)
            warning_report = quality.inspect_manifest(warning_path)
            success_report = quality.inspect_manifest(success_path)

        self.assertEqual(blocker_report.status, "blocker")
        self.assertTrue(blocker_report.has_blockers)
        self.assertTrue(all(issue.guidance for issue in blocker_report.issues))
        self.assertEqual(warning_report.status, "warning")
        self.assertFalse(warning_report.has_blockers)
        self.assertTrue(warning_report.has_warnings)
        warning_text = repr(warning_report.issues)
        self.assertEqual(warning_report.issues[0].code, "unvalidated_extra_columns")
        self.assertTrue(warning_report.issues[0].guidance)
        self.assertNotIn("private-extra-header", warning_text)
        self.assertNotIn("private-extra-value", warning_text)
        self.assertEqual(success_report.status, "success")
        self.assertFalse(success_report.has_blockers)
        self.assertFalse(success_report.has_warnings)

    def test_empty_manifest_is_not_reported_as_clean(self):
        quality = self.quality_module()
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_manifest(directory, "record_id,group_id,split,label\n")

            report = quality.inspect_manifest(path)

        self.assertEqual(report.row_count, 0)
        self.assertIn("no_records", {issue.code for issue in report.issues})

    def test_detects_duplicate_records_and_group_split_leakage_without_identifiers(self):
        quality = self.quality_module()
        content = (
            "record_id,group_id,split,label\n"
            "private-record-a,private-group,train,private-label\n"
            "private-record-a,private-group,train,private-label\n"
            "private-record-b,private-group,test,private-label\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            report = quality.inspect_manifest(self.write_manifest(directory, content))

        issues = {issue.code: issue for issue in report.issues}
        self.assertEqual(issues["duplicate_record_id"].count, 1)
        self.assertEqual(issues["duplicate_record_id"].line_numbers, (2, 3))
        self.assertEqual(issues["group_split_overlap"].count, 1)
        self.assertEqual(issues["group_split_overlap"].line_numbers, (2, 3, 4))
        issue_text = repr(report.issues)
        self.assertNotIn("private-record", issue_text)
        self.assertNotIn("private-group", issue_text)
        self.assertNotIn("private-label", issue_text)

    def test_reports_missing_values_and_malformed_row_width_by_line_number(self):
        quality = self.quality_module()
        content = (
            "record_id,group_id,split,label\n"
            "r-1,g-1,train,alpha\n"
            "r-2,,validation,beta,unexpected\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            report = quality.inspect_manifest(self.write_manifest(directory, content))

        issues = {issue.code: issue for issue in report.issues}
        self.assertEqual(issues["empty_required_value"].count, 1)
        self.assertEqual(issues["empty_required_value"].line_numbers, (3,))
        self.assertEqual(issues["row_width"].count, 1)
        self.assertEqual(issues["row_width"].line_numbers, (3,))

    def test_rejects_unterminated_quoted_field_without_echoing_values(self):
        quality = self.quality_module()
        content = 'record_id,group_id,split,label\nprivate-record,g-1,train,"private-label\n'
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_manifest(directory, content)

            with self.assertRaises(quality.ManifestQualityError) as raised:
                quality.inspect_manifest(path)

        self.assertEqual(raised.exception.code, "invalid_csv")
        self.assertEqual(raised.exception.severity, "blocker")
        self.assertNotIn("private-record", str(raised.exception))
        self.assertNotIn("private-label", str(raised.exception))

    def test_accepts_valid_quoted_multiline_field_as_one_record(self):
        quality = self.quality_module()
        content = 'record_id,group_id,split,label\nr-1,g-1,train,"alpha,\nbeta"\n'
        with tempfile.TemporaryDirectory() as directory:
            report = quality.inspect_manifest(self.write_manifest(directory, content))

        self.assertEqual(report.status, "success")
        self.assertEqual(report.row_count, 1)
        self.assertEqual(report.label_category_count, 1)

    def test_rejects_missing_required_columns_with_a_safe_error(self):
        quality = self.quality_module()
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_manifest(directory, "record_id,split\nr-1,train\n")

            with self.assertRaises(quality.ManifestQualityError) as raised:
                quality.inspect_manifest(path)

        self.assertEqual(raised.exception.code, "missing_required_columns")
        self.assertEqual(raised.exception.severity, "blocker")
        self.assertTrue(raised.exception.guidance)
        self.assertIn("group_id", str(raised.exception))
        self.assertNotIn(str(path), str(raised.exception))

    def test_reports_invalid_utf8_without_echoing_file_contents(self):
        quality = self.quality_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.csv"
            path.write_bytes(b"record_id,group_id,split,label\n\xff\xfe\n")

            with self.assertRaises(quality.ManifestQualityError) as raised:
                quality.inspect_manifest(path)

        self.assertEqual(raised.exception.code, "invalid_encoding")
        self.assertEqual(raised.exception.severity, "blocker")
        self.assertTrue(raised.exception.guidance)
        self.assertNotIn("\\xff", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
